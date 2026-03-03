"""Regulations data management"""
import json
from pathlib import Path
from flask import current_app


def get_regulations() -> list:
    """Get regulations from regulations.json
    
    Returns:
        List of regulation dicts with 'question' and 'answer' keys
    """
    try:
        # Look for regulations.json in the root or database/seeds folder
        possible_paths = [
            Path(current_app.root_path).parent / 'regulations.json',
            Path(current_app.root_path).parent / 'database' / 'seeds' / 'regulations.json',
        ]
        
        path = None
        for p in possible_paths:
            if p.exists():
                path = p
                break
        
        if not path:
            return []

        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if not isinstance(data, list):
            data = []

        # Normalize items to have question/answer keys
        normalized = []
        for item in data:
            q = str(item.get('question', '')).strip()
            a = str(item.get('answer', '')).strip()
            if q or a:
                normalized.append({'question': q, 'answer': a})

        return normalized

    except Exception as e:
        raise Exception(f'Failed to load regulations: {str(e)}')
