"""Read local credentials without executing shell syntax or logging secret values."""
import os
import re
from pathlib import Path

NAMES={'DISASTER_API_KEY','DISASTER_BASE_URL','DISASTER_MODEL','DEEPSEEK_API_KEY','DEEPSEEK_BASE_URL','DEEPSEEK_MODEL'}


def load_local_env(path=None):
    path=Path(path or Path(__file__).resolve().parents[1]/'.env')
    values={}
    if path.exists():
        content=path.read_text(encoding='utf-8-sig').strip()
        if re.fullmatch(r'sk-[A-Za-z0-9_-]+',content):values['DEEPSEEK_API_KEY']=content
        else:
            for line in content.splitlines():
                if line.lstrip().startswith('#') or '=' not in line:continue
                name,value=line.split('=',1);name=name.strip().removeprefix('export ')
                if name in NAMES:values[name]=value.strip().strip('\"\'')
    for name,value in values.items():
        if value:os.environ.setdefault(name,value)
    for field in ('API_KEY','BASE_URL','MODEL'):
        value=os.getenv('DEEPSEEK_'+field)
        if value:os.environ.setdefault('DISASTER_'+field,value)
    if os.getenv('DISASTER_API_KEY'):
        os.environ.setdefault('DISASTER_BASE_URL','https://api.deepseek.com')
        os.environ.setdefault('DISASTER_MODEL','deepseek-v4-flash')
    return bool(os.getenv('DISASTER_API_KEY') and os.getenv('DISASTER_MODEL'))
