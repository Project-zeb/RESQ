import sys


def patch_basecontext_copy():
    if sys.version_info < (3, 14):
        return

    try:
        from django.template import context as django_context
    except Exception:
        return

    BaseContext = django_context.BaseContext

    def _safe_copy(self):
        duplicate = self.__class__.__new__(self.__class__)
        if hasattr(self, "__dict__"):
            duplicate.__dict__ = self.__dict__.copy()
        duplicate.dicts = self.dicts[:]
        return duplicate

    BaseContext.__copy__ = _safe_copy
