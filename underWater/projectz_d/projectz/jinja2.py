from jinja2 import Environment, select_autoescape

from core.web import url


def environment(**options):
    options.setdefault("autoescape", select_autoescape(["html", "xml"]))
    env = Environment(**options)
    env.globals.update(url=url)
    return env
