import os

class PathUtils:
    @staticmethod
    def normalize(path: str):
        if not path:
            return ""
        return os.path.normpath(path).replace("\\", "/")
