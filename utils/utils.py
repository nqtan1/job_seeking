import json 
from typing import Dict, Any

from pathlib import Path
from pydantic import BaseModel

# Save json file
def save_json(data: Any, file_path: str) -> None:
    # Convert Pydantic model to dict
    if isinstance(data, BaseModel):
        data = data.model_dump()
    
    # Create directory if it doesn't exist
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# Load json file
def load_json(file_path: str) -> Dict:
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

# Save txt file
def save_txt(content: str, file_path: str) -> None:
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

# Load txt file
def load_txt(file_path: str) -> str:
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()