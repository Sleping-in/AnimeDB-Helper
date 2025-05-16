# Mock xbmcgui module for development purposes
class Dialog:
    def notification(self, title, message, icon):
        print(f"NOTIFICATION: {title} - {message}")
