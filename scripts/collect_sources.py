"""Download publicly available source snapshots; preserve bytes and SHA256."""
from pathlib import Path
import hashlib
import json
import subprocess
import urllib.request
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    dict(id='national2024', title='国家自然灾害救助应急预案', version='国办函〔2024〕11号',
         published_at='2024-02-05T18:05:00+08:00', issued_at='2024-01-20', kind='policy',
         url='https://yjgl.xinjiang.gov.cn/xjyjgl/c112886/202402/c0f2c9158adf492dab74fdcf5f2fc02f.shtml'),
    dict(id='sichuan2024', title='四川省突发地质灾害应急预案（2024年度修订）', version='川地灾指发〔2024〕2号',
         published_at='2024-05-28T23:59:59+08:00', issued_at='2024-05-23', kind='policy',
         url='https://dnr.sc.gov.cn/scdnr/scgsgg/2024/5/28/0da2f9d9af9d40b6a912749609be74f2/files/《四川省突发地质灾害应急预案（2024年度修订）》.pdf'),
    dict(id='xinhua0804', title='新华视点｜全力以赴抢险——四川康定山洪泥石流灾害救援进行时',
         published_at='2024-08-04T21:39:21+08:00', publication_precision='second', kind='case',
         url='https://sc.news.cn/20240804/9aa6037c17e649599b9cee3283b7386f/c.html'),
    dict(id='kangding0804', title='最新！康定姑咱“8·03”特大山洪泥石流灾害抢险救援有序推进',
         published_at='2024-08-04T20:24:51+08:00', kind='case',
         url='https://www.kangding.gov.cn/xsl_jyqk/article/599752'),
]


def main():
    from bs4 import BeautifulSoup
    from pypdf import PdfReader
    out = ROOT / 'data/sources'
    out.mkdir(parents=True, exist_ok=True)
    for source in SOURCES:
        extension = '.pdf' if source['url'].endswith('.pdf') else '.html'
        target = out / (source['id'] + extension)
        url = quote(source['url'], safe=':/%?=&')
        if not target.exists():
            try:
                with urllib.request.urlopen(url, timeout=30) as response:
                    target.write_bytes(response.read())
            except Exception:
                subprocess.run(['curl.exe', '--fail', '-L', '--retry', '2', '--max-time', '30', '-sS', url, '-o', str(target)], check=True)
        if extension == '.pdf':
            reader = PdfReader(target)
            text = '\n'.join(f'\n[PDF page {i+1}]\n' + (p.extract_text() or '') for i, p in enumerate(reader.pages))
        else:
            soup = BeautifulSoup(target.read_bytes().decode('utf-8'), 'html.parser')
            for tag in soup(['script', 'style']):
                tag.decompose()
            text = soup.get_text('\n', strip=True)
        (out / (source['id'] + '.txt')).write_text(text, encoding='utf-8')
        source['sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
        source['snapshot'] = str(target.relative_to(ROOT)).replace('\\', '/')
        source['retrieved_at'] = '2026-09-06'
        source['provenance'] = 'public_source'
        print(source['id'], len(text), source['sha256'][:12])
    (ROOT / 'data/sources.json').write_text(json.dumps(SOURCES, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
