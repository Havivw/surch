import sys

from .. import utils, logger
from . import vault

lgr = logger.init()
KEY_LIST = ('.*password.*', '.*key.*', '.*secret.*', '.*id.*', '.*endpoint.*',
            '.*tenant.*', '.*api.*')


def plugins_handle(plugins_list, config_file):
    if plugins_list:
        lowercase_list = []
        for value in plugins_list:
            value = value.encode('ascii')
            lowercase_list.append(value.lower())
            if config_file:
                pass
            else:
                lgr.error("Used a config file when you "
                          "want to use '--source/--pager'.")
                sys.exit(1)
        return lowercase_list
    else:
        return ('')


def vault_trigger(config_file=None):
    if config_file:
        conf_var = utils.read_config_file(config_file)
        try:
            conf_var = conf_var['vault']
        except KeyError as e:
            lgr.error('Vault error: '
                      'can\'t run vault - no "{0}" '
                      'in config file.'.format(e.message))
        try:
            key_list = conf_var['key_list']
        except KeyError:
            key_list = KEY_LIST
        try:
            return vault.get_search_list(
                vault_url=conf_var['vault_url'],
                vault_token=conf_var['vault_token'],
                secret_path=conf_var['secret_path'],
                key_list=key_list)
        except KeyError as e:
            lgr.error('Vault error: can\'t run vault - "{0}" '
                      'argument is missing.'.format(e.message))
            sys.exit(1)
        except TypeError as e:
            lgr.error('Vault error: '
                      'can\'t run vault - {0}.'.format(e.message))
    else:
        lgr.error('Vault error: Config file is missing.')
        sys.exit(1)
