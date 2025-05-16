# Mock xbmc module for development purposes
class LOGINFO:
    pass

def log(message, level):
    print(f"LOG: {message}")
