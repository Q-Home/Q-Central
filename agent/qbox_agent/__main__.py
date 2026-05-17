import json

from . import agent


_original_installed_apps = agent.installed_apps


def _app_as_string(app):
    if isinstance(app, str):
        return app
    if isinstance(app, dict) and app.get('type') == 'loxberry_plugin':
        name = app.get('name') or app.get('folder') or app.get('id')
        if not name:
            return None
        label = f'LoxBerry: {name}'
        if app.get('version'):
            label += f" {app.get('version')}"
        if app.get('enabled') is False:
            label += ' (disabled)'
        return label
    if isinstance(app, dict):
        name = app.get('name') or app.get('id')
        return name or json.dumps(app, sort_keys=True)
    return str(app)


def installed_apps():
    return [value for value in (_app_as_string(app) for app in _original_installed_apps()) if value]


agent.installed_apps = installed_apps
agent.main()
