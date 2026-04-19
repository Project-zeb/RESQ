import os
from urllib.parse import urlencode

from django.templatetags.static import static as django_static
from django.urls import NoReverseMatch, reverse

URL_PATH_PARAMS = {
    "mobile_sos_app_download_version": ["apk_filename"],
    "mobile_analysis_asset": ["asset_id"],
}


def _build_external_url(path, request=None):
    if request is not None:
        try:
            return request.build_absolute_uri(path)
        except Exception:
            pass

    base_url = os.getenv("APP_BASE_URL")
    if not base_url:
        scheme = os.getenv("APP_URL_SCHEME", "http")
        host = os.getenv("APP_HOST", "127.0.0.1")
        port = os.getenv("PORT", "2000")
        if host in {"127.0.0.1", "localhost"}:
            base_url = f"{scheme}://{host}:{port}"
        else:
            base_url = f"{scheme}://{host}"
            if port and port not in {"80", "443"}:
                base_url = f"{base_url}:{port}"
    return base_url.rstrip("/") + path


def url(name, request=None, _external=False, **values):
    if name == "static":
        filename = values.get("filename") or values.get("path") or ""
        return django_static(filename)

    path_kwargs = {}
    query_params = {}
    for key, value in values.items():
        if value is None:
            continue
        if key in URL_PATH_PARAMS.get(name, []):
            path_kwargs[key] = value
        else:
            query_params[key] = value

    try:
        path = reverse(name, kwargs=path_kwargs or None)
    except NoReverseMatch:
        path = str(name)

    if query_params:
        path = f"{path}?{urlencode(query_params, doseq=True)}"

    if _external:
        return _build_external_url(path, request=request)
    return path
