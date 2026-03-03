"""Ranking data management"""
import json
from pathlib import Path
from flask import current_app


def get_rankings() -> list:
    """Get rankings from rankings.json sorted by points descending
    
    Returns:
        List of ranking dicts with 'team', 'points', 'image' keys
    """
    try:
        # Look for rankings.json in the root or database/seeds folder
        possible_paths = [
            Path(current_app.root_path).parent / 'rankings.json',
            Path(current_app.root_path).parent / 'database' / 'seeds' / 'rankings.json',
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

        normalized = []
        for item in data:
            team = str(item.get('team', '')).strip()
            pts = item.get('points', 0)
            img = item.get('image')
            if team:
                try:
                    pts = int(pts)
                except Exception:
                    pts = 0
                normalized.append({'team': team, 'points': pts, 'image': img})

        normalized.sort(key=lambda x: x['points'], reverse=True)
        return normalized

    except Exception as e:
        raise Exception(f'Failed to load rankings: {str(e)}')
