import re

# ==========================================
# 1. PRE-PROCESSING & DICTIONARY
# ==========================================

BPS_STOPWORDS = {
    'jumlah', 'banyaknya', 'menurut', 'total', 'dan', 'yang', 'dari', 
    'kabupaten', 'tasikmalaya', 'kecamatan', 'pada', 'tahun', 'di'
}

BPS_SYNONYMS = {
    'pria': 'laki-laki',
    'wanita': 'perempuan',
    'desa': 'desa/kelurahan',
    'kelurahan': 'desa/kelurahan',
    'medis': 'dokter',
    'puskesmas': 'pusat kesehatan masyarakat',
    'pns': 'pegawai negeri sipil',
    'asn': 'aparatur sipil negara',
    'pppk': 'pegawai pemerintah dengan perjanjian kinerja',
    'sd': 'sekolah dasar',
    'smp': 'sekolah menengah pertama',
    'sma': 'sekolah menengah atas',
    'pt': 'perguruan tinggi',
    'pdrb': 'produk domestik regional bruto',
    'pma': 'penanaman modal asing',
    'pmdn': 'penanaman modal dalam negeri',
    'tpt': 'tingkat pengangguran terbuka',
    'tpak': 'tingkat partisipasi angkatan kerja',
}

BPS_ANTONYMS = [
    ({'laki', 'pria', 'laki-laki'}, {'perempuan', 'wanita'}),
    ({'umum'}, {'khusus', 'bersalin'}),
    ({'negeri'}, {'swasta'}),
    ({'pusat'}, {'daerah', 'provinsi', 'kabupaten', 'kota'}),
    ({'impor'}, {'ekspor'}),
    ({'penerimaan'}, {'pengeluaran'}),
]

def preprocess_text(text):
    if not text:
        return ""
    # Lowercase
    text = text.lower()
    # Remove years, brackets
    text = re.sub(r'\b20\d{2}\b|\b\d{4}-\d{4}\b', '', text)
    text = re.sub(r'\[.*?\]', '', text)
    # Tokenize
    words = re.findall(r'\b[a-z0-9]+\b', text)
    
    processed_words = []
    for w in words:
        if w in BPS_STOPWORDS:
            continue
        # Apply synonym
        w = BPS_SYNONYMS.get(w, w)
        processed_words.append(w)
        
    return ' '.join(processed_words)

# ==========================================
# 2. JARO-WINKLER ALGORITHM
# ==========================================

def jaro_distance(s1, s2):
    if s1 == s2: return 1.0
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0: return 0.0
    
    max_dist = (max(len1, len2) // 2) - 1
    match = 0
    
    hash_s1 = [0] * len1
    hash_s2 = [0] * len2
    
    for i in range(len1):
        for j in range(max(0, i - max_dist), min(len2, i + max_dist + 1)):
            if s1[i] == s2[j] and hash_s2[j] == 0:
                hash_s1[i] = 1
                hash_s2[j] = 1
                match += 1
                break
                
    if match == 0: return 0.0
    
    t = 0
    point = 0
    for i in range(len1):
        if hash_s1[i]:
            while hash_s2[point] == 0:
                point += 1
            if s1[i] != s2[point]:
                t += 1
            point += 1
            
    t /= 2
    return (match / len1 + match / len2 + (match - t) / match) / 3.0

def jaro_winkler(s1, s2):
    jaro_dist = jaro_distance(s1, s2)
    if jaro_dist > 0.7:
        prefix = 0
        for i in range(min(len(s1), len(s2))):
            if s1[i] == s2[i]:
                prefix += 1
            else:
                break
        prefix = min(4, prefix)
        jaro_dist += 0.1 * prefix * (1 - jaro_dist)
    return jaro_dist

# ==========================================
# 3. COLUMN MATCHING (GREEDY 1-TO-1 + UNIT PENALTY)
# ==========================================

def match_columns(target_cols, source_cols):
    """
    Given a list of target KolomTabel objects and source KolomTabel objects,
    returns a mapping: { target_col_id : (source_col_object, final_score) }
    """
    pairs = []
    
    # Calculate all possible pair scores
    for t_col in target_cols:
        t_text = preprocess_text(t_col.indikator.nama)
        for s_col in source_cols:
            s_text = preprocess_text(s_col.indikator.nama)
            
            # If text is empty after preprocessing, fallback to raw text
            if not t_text: t_text = t_col.indikator.nama.lower().strip()
            if not s_text: s_text = s_col.indikator.nama.lower().strip()
            
            if t_text == s_text:
                score = 1.0
            else:
                score = jaro_winkler(t_text, s_text)
            
            # Subset Bonus: if all words in one are in the other, boost score
            t_words = set(t_text.split())
            s_words = set(s_text.split())
            if t_words and s_words:
                if t_words.issubset(s_words) or s_words.issubset(t_words):
                    score = max(score, 0.85)
            
            # Apply Unit Penalty
            t_sat = t_col.satuan.lower().strip() if t_col.satuan else ''
            s_sat = s_col.satuan.lower().strip() if s_col.satuan else ''
            
            # Only penalize if both have units and they are completely different
            if t_sat and s_sat and t_sat != s_sat:
                score -= 0.25
                
            # Apply Antonym Penalty
            if score > 0.5:
                for a_set1, a_set2 in BPS_ANTONYMS:
                    if (t_words.intersection(a_set1) and s_words.intersection(a_set2)) or \
                       (t_words.intersection(a_set2) and s_words.intersection(a_set1)):
                        score -= 0.40 # Heavy penalty for conflicting concepts
                        
            if score > 0:
                pairs.append((score, t_col, s_col))
                
    # Sort pairs by highest score first
    pairs.sort(key=lambda x: x[0], reverse=True)
    
    assigned_targets = set()
    assigned_sources = set()
    mapping = {}
    
    # Greedy Bipartite Matching
    for score, t_col, s_col in pairs:
        if t_col.id not in assigned_targets and s_col.id not in assigned_sources:
            if score > 0.82:  # Threshold increased from 0.75 to 0.82 to avoid bad matches
                mapping[t_col.id] = (s_col, score)
                assigned_targets.add(t_col.id)
                assigned_sources.add(s_col.id)
                
    return mapping
