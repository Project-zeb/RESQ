from django.contrib.auth.hashers import BasePasswordHasher, mask_hash
from werkzeug.security import check_password_hash, generate_password_hash


class WerkzeugPasswordHasher(BasePasswordHasher):
    algorithm = "werkzeug"

    def encode(self, password, salt=None):
        if password is None:
            raise ValueError("password must not be None")
        hashed = generate_password_hash(password)
        return f"{self.algorithm}${hashed}"

    def verify(self, password, encoded):
        if not encoded:
            return False
        try:
            algorithm, legacy_hash = encoded.split("$", 1)
        except ValueError:
            return False
        if algorithm != self.algorithm:
            return False
        return check_password_hash(legacy_hash, password)

    def safe_summary(self, encoded):
        algorithm, legacy_hash = encoded.split("$", 1) if encoded else (self.algorithm, "")
        return {
            "algorithm": algorithm,
            "hash": mask_hash(legacy_hash),
        }

    def must_update(self, encoded):
        return True
