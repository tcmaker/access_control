class AuthPlugin(object):
    def get_configuration_schema(self) -> (str, dict, bool):
        """
        :return: (plugin name, config schema, config required)
        """
        pass

    def read_configuration(self, config):
        pass

    def on_load(self):
        pass

    def on_close(self):
        pass

    def refresh_database(self):
        pass


    def on_scan(self, credential_type, credential_value, scanner, facility) -> (bool, str, str):
        """
        :rtype: (bool: grant or not,str: the member id, str: the authorization guid)
        """
        return (False,None,None)
