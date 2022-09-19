class Playlist:
    def __init__(self, id, name, *, parent=None, auto=False, tracks=None, query=None):
        self.id = id
        self.name = name
        self.parent = parent
        self.auto = bool(auto)
        self.tracks = tracks if tracks is not None else []
        self.query = query

    @classmethod
    def from_db_row(cls, row):
        id, name, parent, _, auto, *_ = row
        return cls(id, name, parent=parent, auto=auto, query=_[-1])
