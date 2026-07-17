def get_db():
    class Database:
        def get_item(self):
            return [
                {"id": 1, "name": "Ноутбук", "description": "This is item 1."},
            ]

    return Database()
      