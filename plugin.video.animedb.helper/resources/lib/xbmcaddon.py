# Mock xbmcaddon module for development purposes
class Addon:
    def getAddonInfo(self, key):
        return "mock_value"

    def getSetting(self, key):
        return "mock_setting"

    def getSettingBool(self, key):
        return False
