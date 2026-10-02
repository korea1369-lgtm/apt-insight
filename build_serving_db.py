"""Usage: python build_serving_db.py --source original.db --output serving_master.db --main main.py"""
from db_tools import pipeline
if __name__ == '__main__':
    pipeline('serving')
