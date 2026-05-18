#!/usr/bin/env python3
"""
Daily paper watcher — Cell, Nature, Science
Uses Groq (free) for one-line summaries
Stores result to GitHub Gist
"""
import requests, json, os, re
from datetime import date
from xml.etree import ElementTree as ET

GIST_ID   = os.environ['GIST_ID']
GH_TOKEN  = os.environ['GH_TOKEN']
GROQ_KEY  = os.environ['GROQ_KEY']
TODAY     = str(date.today())

JOURNALS = {
    'Nature':               '0028-0836',
    'Science':              '0036-8075',
    'Cell':                 '0092-8674',
    'Nature Methods':       '1548-7091',
}

# ── 1. Fetch from PubMed (free, no key needed) ─────────────────
def fetch_papers(issn, journal_name, max_results=4):
    # With this (searches last 3 days):
    from datetime import date, timedelta
    THREE_DAYS_AGO = str(date.today() - timedelta(days=3))

    query = (
        f'{issn}[ISSN] AND '
        f'("{THREE_DAYS_AGO}"[PDAT]:"{TODAY}"[PDAT]) AND '
        f'(biology OR genomics OR transcriptomics OR single-cell OR '
        f'RNA-seq OR proteomics OR metabolomics OR CRISPR OR '
        f'neuroscience OR stem cell OR cancer OR epigenetics)'
    )
    search = requests.get(
        'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi',
        params={
            'db':'pubmed', 'term':query,
            'retmax':max_results, 'retmode':'json', 'sort':'date'
        }, timeout=15
    )
    ids = search.json().get('esearchresult',{}).get('idlist',[])
    if not ids: return []

    xml  = requests.get(
        'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi',
        params={'db':'pubmed','id':','.join(ids),'retmode':'xml'},
        timeout=15
    ).text
    root    = ET.fromstring(xml)
    papers  = []

    for article in root.findall('.//PubmedArticle'):
        try:
            title = re.sub(r'<[^>]+>','',
                article.findtext('.//ArticleTitle','').strip())

            abstract = ' '.join(
                (p.text or '')
                for p in article.findall('.//AbstractText')
            ).strip()[:1000]
            if not title or not abstract:
                continue

            authors = article.findall('.//Author')
            names   = []
            for a in authors[:3]:
                ln = a.findtext('LastName','')
                fn = a.findtext('ForeName','')
                if ln: names.append(f'{ln} {fn[:1]}.' if fn else ln)
            author_str = ', '.join(names)
            if len(authors) > 3: author_str += ' et al.'

            pmid     = article.findtext('.//PMID','')
            doi_node = article.find('.//ArticleId[@IdType="doi"]')
            doi      = doi_node.text if doi_node is not None else ''
            url      = (f'https://doi.org/{doi}' if doi
                        else f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/')

            papers.append({
                'title':    title,
                'authors':  author_str,
                'abstract': abstract,
                'url':      url,
                'pmid':     pmid,
                'journal':  journal_name,
            })
        except Exception as e:
            print(f'  Parse error: {e}')
            continue
    return papers

# ── 2. Summarise with Groq (free) ──────────────────────────────
def summarise_groq(abstract):
    if not abstract.strip():
        return 'No abstract available.'
    try:
        resp = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {GROQ_KEY}',
                'Content-Type':  'application/json',
            },
            json={
                'model':      'llama-3.1-8b-instant',  # free, very fast
                'max_tokens': 60,
                'temperature': 0.3,
                'messages': [{
                    'role': 'system',
                    'content': (
                        'Summarise this biology paper abstract in exactly '
                        'one plain-English sentence under 25 words. '
                        'Start with the key finding. No preamble.'
                    )
                },{
                    'role':    'user',
                    'content': abstract
                }]
            },
            timeout=20
        )
        return resp.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f'  Groq error: {e}')
        # Fallback: first 25 words of abstract
        words = abstract.split()[:25]
        return ' '.join(words) + '…'

# ── 3. Save to GitHub Gist ─────────────────────────────────────
def save_to_gist(data):
    resp = requests.patch(
        f'https://api.github.com/gists/{GIST_ID}',
        headers={
            'Authorization': f'Bearer {GH_TOKEN}',
            'Accept':        'application/vnd.github+json',
        },
        json={
            'description': f'Jayce paper digest — {TODAY}',
            'files': {
                'paper_digest.json': {
                    'content': json.dumps(data, indent=2, ensure_ascii=False)
                }
            }
        },
        timeout=20
    )
    return resp.status_code

# ── 4. Main ────────────────────────────────────────────────────
def main():
    print(f'Starting paper watch for {TODAY}...')
    all_papers = []

    for journal, issn in JOURNALS.items():
        print(f'Fetching {journal}...')
        papers = fetch_papers(issn, journal, max_results=4)
        print(f'  Found {len(papers)} papers')

        for p in papers:
            print(f'  Summarising: {p["title"][:55]}...')
            p['summary'] = summarise_groq(p['abstract'])
            del p['abstract']   # don't store full abstract in gist
            all_papers.append(p)

    result = {
        'date':   TODAY,
        'count':  len(all_papers),
        'papers': all_papers,
    }

    status = save_to_gist(result)
    print(f'\nDone! {len(all_papers)} papers saved to Gist (HTTP {status})')

    # Print preview
    for p in all_papers[:3]:
        print(f'\n[{p["journal"]}] {p["title"][:60]}')
        print(f'  → {p["summary"]}')

if __name__ == '__main__':
    main()
