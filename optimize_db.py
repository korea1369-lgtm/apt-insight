"""Usage: python optimize_db.py --source original.db --output optimized.db --main main.py"""
from db_tools import pipeline
if __name__ == '__main__':
    pipeline('optimize')
