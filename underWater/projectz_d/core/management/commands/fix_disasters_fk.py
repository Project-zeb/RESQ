from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Remove legacy FK constraints on Disasters and map legacy user IDs to auth_user IDs."

    def handle(self, *args, **options):
        vendor = connection.vendor
        if vendor == "sqlite":
            self._fix_sqlite()
        else:
            self._fix_mysql()

    def _fix_sqlite(self):
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys=OFF")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS Disasters_new (
                    Disaster_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    verify_status BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    media BLOB,
                    media_type TEXT CHECK(media_type IN ('video','image')),
                    reporter_id INTEGER NOT NULL,
                    admin_id INTEGER,
                    disaster_type VARCHAR(100) NOT NULL,
                    description TEXT,
                    latitude DECIMAL(10, 8) NOT NULL,
                    longitude DECIMAL(11, 8) NOT NULL,
                    address_text VARCHAR(255)
                );
                """
            )
            cursor.execute(
                """
                INSERT INTO Disasters_new (
                    Disaster_id, verify_status, created_at, media, media_type,
                    reporter_id, admin_id, disaster_type, description,
                    latitude, longitude, address_text
                )
                SELECT
                    Disaster_id, verify_status, created_at, media, media_type,
                    reporter_id, admin_id, disaster_type, description,
                    latitude, longitude, address_text
                FROM Disasters;
                """
            )
            cursor.execute("DROP TABLE Disasters")
            cursor.execute("ALTER TABLE Disasters_new RENAME TO Disasters")
            cursor.execute("PRAGMA foreign_keys=ON")

            # Map legacy IDs to auth_user IDs using core_userprofile
            cursor.execute(
                """
                UPDATE Disasters
                SET reporter_id = (
                    SELECT user_id FROM core_userprofile WHERE legacy_user_id = Disasters.reporter_id
                )
                WHERE reporter_id IN (
                    SELECT legacy_user_id FROM core_userprofile WHERE legacy_user_id IS NOT NULL
                );
                """
            )
            cursor.execute(
                """
                UPDATE Disasters
                SET admin_id = (
                    SELECT user_id FROM core_userprofile WHERE legacy_user_id = Disasters.admin_id
                )
                WHERE admin_id IN (
                    SELECT legacy_user_id FROM core_userprofile WHERE legacy_user_id IS NOT NULL
                );
                """
            )
        self.stdout.write(self.style.SUCCESS("Disasters table rebuilt without legacy FK and IDs remapped."))

    def _fix_mysql(self):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT CONSTRAINT_NAME
                FROM information_schema.KEY_COLUMN_USAGE
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'Disasters'
                  AND REFERENCED_TABLE_NAME IN ('Users', 'Users_legacy')
                """
            )
            constraints = [row[0] for row in cursor.fetchall()]
            for name in constraints:
                cursor.execute(f"ALTER TABLE Disasters DROP FOREIGN KEY {name}")

            cursor.execute(
                """
                UPDATE Disasters d
                JOIN core_userprofile p ON d.reporter_id = p.legacy_user_id
                SET d.reporter_id = p.user_id
                WHERE p.legacy_user_id IS NOT NULL;
                """
            )
            cursor.execute(
                """
                UPDATE Disasters d
                JOIN core_userprofile p ON d.admin_id = p.legacy_user_id
                SET d.admin_id = p.user_id
                WHERE p.legacy_user_id IS NOT NULL;
                """
            )
        self.stdout.write(self.style.SUCCESS("Disasters FK removed and IDs remapped (MySQL)."))
