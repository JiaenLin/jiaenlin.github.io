#!/usr/bin/env python3
"""
Daily paper watcher — Nature, Science, Cell + specialist journals
Uses NCBI API key (10 req/sec) + Groq for summaries
Stores result to GitHub Gist
"""
import requests, json, os, re, time, sys
from datetime import datetime, date, timedelta, timezone
from xml.etree import ElementTree as ET

MONTH_NUM = {
    'Jan':'01','Feb':'02','Mar':'03','Apr':'04','May':'05','Jun':'06',
    'Jul':'07','Aug':'08','Sep':'09','Oct':'10','Nov':'11','Dec':'12',
    'January':'01','February':'02','March':'03','April':'04','June':'06',
    'July':'07','August':'08','September':'09','October':'10','November':'11','December':'12',
}

def pub_date_sort_key(pub_date):
    parts = pub_date.split()
    year  = parts[0] if parts else '0000'
    month = MONTH_NUM.get(parts[1].split('-')[0], '00') if len(parts) > 1 else '00'
    day   = parts[2].zfill(2) if len(parts) > 2 else '00'
    return f'{year}-{month}-{day}'

# ── Credentials ────────────────────────────────────────────────
GIST_ID  = os.environ.get('GIST_ID',  '')
GH_TOKEN = os.environ.get('GH_TOKEN', '')
GROQ_KEY = os.environ.get('GROQ_KEY', '')
NCBI_KEY = os.environ.get('NCBI_KEY', '')

_now  = datetime.now(timezone.utc) + timedelta(hours=8)  # SGT = UTC+8
TODAY = _now.strftime('%Y-%m-%d')
FROM  = (_now - timedelta(days=7)).strftime('%Y-%m-%d')

# ── Broad journals: need biology keyword filter ────────────────
BROAD_JOURNALS = {
    'Nature':                       'Nature',
    'Science':                      'Science',
    'Nature Computational Science': 'Nat Comput Sci',
    'Nature Machine Intelligence':  'Nat Mach Intell',  
}

# ── Specialist biology journals: fetch all papers ──────────────
SPECIALIST_JOURNALS = {
    'Cell':                  'Cell',
    'Nature Methods':        'Nat Methods',
    'Nature Biotechnology':  'Nat Biotechnol',
    'Cell Metabolism':       'Cell Metab',
    'Nature Metabolism':     'Nat Metab',
    'Cell Stem Cell':        'Cell Stem Cell',
    'Nature Cell Biology':   'Nat Cell Biol',
    'Nature Neuroscience':   'Nat Neurosci',
    'Nature Genetics':       'Nat Genet',
    'Nature Medicine':       'Nat Med',
    'Circulation':           'Circulation',
    'Neuron':                'Neuron',
    'Cancer Cell':           'Cancer Cell',  
}

# ── Biology filter — only for Nature & Science ────────────────
BIO_TERMS = (
    # Must be molecular/cellular biology
    '"molecular biology" OR "cell biology" OR "systems biology" OR '
    'genomics OR transcriptomics OR proteomics OR metabolomics OR '
    'epigenetics OR "gene expression" OR chromatin OR '

    # Sequencing methods — very specific
    '"single-cell" OR "scRNA-seq" OR "snRNA-seq" OR "spatial transcriptomics" OR '
    '"multi-omics" OR "ATAC-seq" OR "ChIP-seq" OR "RNA sequencing" OR '

    # Functional genomics
    'CRISPR OR "gene editing" OR "transcription factor" OR '
    '"gene regulation" OR "enhancer" OR "epigenome" OR '

    # Specific biology subfields
    'neuroscience OR "stem cell" OR "organoid" OR '
    '"cell differentiation" OR "cell signaling" OR '
    '"cancer biology" OR "tumor microenvironment" OR '

    # Specific omics/metabolism
    '"single cell" OR "cell atlas" OR ferroptosis OR '
    '"metabolic pathway" OR mitochondria OR microbiome OR '
    '"heart failure" OR cardiomyocyte OR "immune cell"'
)
# ── Post-fetch biology title filter ───────────────────────────
EXCLUDE_KEYWORDS = [
    'switching device', 'antiferromagnet', 'quantum', 'photon',
    'climate', 'earthquake', 'asteroid', 'telescope', 'physics',
    'wastewater surveillance', 'public health policy', 'administration cuts',
    'CDC cuts', 'political', 'election', 'economics', 'fossil fuel',
    'semiconductor', 'material science', 'superconductor',
]
# ── Helper: post filter ────────────────────────────
def is_biology(title, abstract):
    text = (title + ' ' + abstract).lower()
    # Reject if any hard-exclude keyword found
    if any(kw.lower() in text for kw in EXCLUDE_KEYWORDS):
        return False
    return True
# ── Helper: add NCBI key to params ────────────────────────────
def ncbi_params(extra: dict) -> dict:
    p = {**extra}
    if NCBI_KEY:
        p['api_key'] = NCBI_KEY
    return p

# ── 1. Fetch papers from PubMed ────────────────────────────────
def fetch_papers(journal_ta, journal_name, max_results=5, use_bio_filter=True):
    if use_bio_filter:
        query = f'{journal_ta}[TA] AND ("{FROM}"[PDAT]:"{TODAY}"[PDAT]) AND ({BIO_TERMS})'
    else:
        query = f'{journal_ta}[TA] AND ("{FROM}"[PDAT]:"{TODAY}"[PDAT])'

    # Search for IDs
    try:
        r = requests.get(
            'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi',
            params=ncbi_params({
                'db':'pubmed', 'term':query,
                'retmax':max_results, 'retmode':'json', 'sort':'date'
            }),
            timeout=15
        )
        ids = r.json().get('esearchresult', {}).get('idlist', [])
        print(f'  IDs: {ids if ids else "none"}')
    except Exception as e:
        print(f'  Search error: {e}')
        return []

    if not ids:
        return []

    # Polite delay: 0.11s with key (10/sec), 0.4s without (3/sec)
    time.sleep(0.11 if NCBI_KEY else 0.4)

    # Fetch abstracts as XML
    try:
        fetch_r = requests.get(
            'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi',
            params=ncbi_params({
                'db':'pubmed', 'id':','.join(ids), 'retmode':'xml'
            }),
            timeout=15
        )
        xml_text = fetch_r.text

        if not xml_text.strip().startswith('<'):
            print(f'  ⚠️ Invalid response: {xml_text[:150]}')
            return []

        root = ET.fromstring(xml_text)

    except ET.ParseError as e:
        print(f'  ⚠️ XML parse error: {e}')
        return []
    except Exception as e:
        print(f'  ⚠️ Fetch error: {e}')
        return []

    # Parse articles
    papers = []
    for article in root.findall('.//PubmedArticle'):
        try:
            title = re.sub(r'<[^>]+>', '',
                article.findtext('.//ArticleTitle', '').strip())

            abstract = ' '.join(
                (p.text or '') for p in article.findall('.//AbstractText')
            ).strip()[:1000]

            if not title or not abstract:
                continue
            if not is_biology(title, abstract):
                print(f'  ⚠️ Filtered out: {title[:50]}')
                continue
            authors = article.findall('.//Author')
            names   = []
            for a in authors[:3]:
                ln = a.findtext('LastName', '')
                fn = a.findtext('ForeName', '')
                if ln: names.append(f'{ln} {fn[:1]}.' if fn else ln)
            author_str = ', '.join(names)
            if len(authors) > 3: author_str += ' et al.'

            pmid     = article.findtext('.//PMID', '')
            doi_node = article.find('.//ArticleId[@IdType="doi"]')
            doi      = doi_node.text if doi_node is not None else ''
            url      = (f'https://doi.org/{doi}' if doi
                        else f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/')

            pub_year  = article.findtext('.//PubDate/Year', '')
            pub_month = article.findtext('.//PubDate/Month', '')
            pub_day   = article.findtext('.//PubDate/Day', '')
            medline   = article.findtext('.//PubDate/MedlineDate', '')
            if pub_year and pub_month:
                pub_date = f'{pub_year} {pub_month}' + (f' {pub_day}' if pub_day else '')
            elif medline:
                pub_date = medline
            else:
                pub_date = pub_year

            papers.append({
                'title':         title,
                'authors':       author_str,
                'abstract':      abstract,
                'url':           url,
                'pmid':          pmid,
                'journal':       journal_name,
                'pub_date':      pub_date,
                'pub_date_sort': pub_date_sort_key(pub_date) if pub_date else '',
            })
        except Exception as e:
            print(f'  Article parse error: {e}')
            continue

    return papers

# ── 2. Summarise with Groq (free) ──────────────────────────────
def summarise(abstract):
    if not GROQ_KEY:
        return ' '.join(abstract.split()[:22]) + '…'
    try:
        r = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {GROQ_KEY}',
                'Content-Type':  'application/json',
            },
            json={
                'model':       'llama-3.1-8b-instant',
                'max_tokens':  60,
                'temperature': 0.3,
                'messages': [{
                    'role':    'system',
                    'content': (
                        'Summarise this biology paper abstract in exactly '
                        'one plain-English sentence under 25 words. '
                        'Start with the key finding. No preamble.'
                    )
                }, {
                    'role':    'user',
                    'content': abstract
                }]
            },
            timeout=20
        )
        return r.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f'  Groq error: {e}')
        return ' '.join(abstract.split()[:22]) + '…'

# ── 3. Save to GitHub Gist ─────────────────────────────────────
def save_to_gist(data):
    r = requests.patch(
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
    return r.status_code

# ── 4. Main ────────────────────────────────────────────────────
def main():
    print(f'=== Paper Watch {TODAY} ===')
    print(f'Date range : {FROM} → {TODAY}')
    print(f'GIST_ID    : {"✅" if GIST_ID  else "❌ MISSING"}')
    print(f'GH_TOKEN   : {"✅" if GH_TOKEN else "❌ MISSING"}')
    print(f'GROQ_KEY   : {"✅" if GROQ_KEY else "❌ MISSING"}')
    print(f'NCBI_KEY   : {"✅ (10 req/sec)" if NCBI_KEY else "⚠️ not set (3 req/sec)"}')
    print()

    all_papers = []

    # Broad journals — biology filter ON
    for journal_name, journal_ta  in BROAD_JOURNALS.items():
        print(f'Fetching {journal_name} (filtered)...')
        papers = fetch_papers(journal_ta, journal_name, max_results=5, use_bio_filter=True)
        print(f'  → {len(papers)} papers found')
        for p in papers:
            print(f'  Summarising: {p["title"][:55]}...')
            p['summary'] = summarise(p['abstract'])
            del p['abstract']
            all_papers.append(p)

    # Specialist journals — biology filter OFF
    for journal_name, journal_ta in SPECIALIST_JOURNALS.items():
        print(f'Fetching {journal_name} (all papers)...')
        papers = fetch_papers(journal_ta, journal_name, max_results=5, use_bio_filter=False)
        print(f'  → {len(papers)} papers found')
        for p in papers:
            print(f'  Summarising: {p["title"][:55]}...')
            p['summary'] = summarise(p['abstract'])
            del p['abstract']
            all_papers.append(p)

    print(f'\n✅ Total: {len(all_papers)} papers across all journals')

    result = {
        'date':   TODAY,
        'count':  len(all_papers),
        'papers': all_papers,
    }

    # Save
    if not GIST_ID or not GH_TOKEN:
        print('❌ Cannot save — missing GIST_ID or GH_TOKEN')
        sys.exit(1)

    status = save_to_gist(result)
    status_msg = {
        200: '✅ Gist updated successfully',
        404: '❌ Gist not found — wrong GIST_ID?',
        401: '❌ Auth failed — check GH_TOKEN scope (needs "gist")',
    }.get(status, f'❌ Unexpected HTTP {status}')
    print(status_msg)
    if status != 200:
        sys.exit(1)

    # Preview first 3
    print('\n── Preview ──')
    for p in all_papers[:3]:
        print(f'[{p["journal"]}] {p["title"][:60]}')
        print(f'  → {p["summary"]}')
        print()

if __name__ == '__main__':
    main()
