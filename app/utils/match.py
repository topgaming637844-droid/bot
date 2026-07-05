from difflib import SequenceMatcher
import re

def validate_title_match(original_title: str, matched_title: str) -> bool:
    """Verifies that the matched title shares significant keyword containment or a high fuzzy match ratio with the original title."""
    orig_lower = original_title.lower().strip()
    match_lower = matched_title.lower().strip()
    
    # 1. Fuzzy match ratio (strict: 0.70 to avoid false positives)
    ratio = SequenceMatcher(None, orig_lower, match_lower).ratio()
    if ratio >= 0.70:
        return True
        
    # 2. Check substring containment (e.g., "Attack on Titan" is inside "Attack on Titan Season 3")
    if orig_lower in match_lower or match_lower in orig_lower:
        return True
        
    # 3. Check keyword overlap
    orig_words = set(re.findall(r"\w+", orig_lower))
    match_words = set(re.findall(r"\w+", match_lower))
    
    # Common helper words / stop words that shouldn't dictate uniqueness
    stop_words = {"the", "of", "and", "a", "in", "to", "for", "with", "on", "at", "by", "an", "is", "season", "part", "shippuden", "specials", "ova", "movie", "فيلم", "أوفا", "خاصة"}
    orig_keywords = {w for w in orig_words if len(w) > 2 and w not in stop_words}
    match_keywords = {w for w in match_words if len(w) > 2 and w not in stop_words}
    
    if not orig_keywords:
        return True
        
    overlap = orig_keywords.intersection(match_keywords)
    # If original title has important keywords, at least 75% of them must be present in the matched title
    if len(overlap) / len(orig_keywords) >= 0.75:
        return True
        
    return False

def get_best_slug_match(scraper_results, search_title: str) -> str:
    """Selects the best matching anime slug from scraper results, prioritizing exact matches and TV series over movies/OVAs/specials."""
    if not scraper_results:
        return ""
    
    search_lower = search_title.lower().strip()
    search_words = set(re.findall(r"\w+", search_lower))
    
    # ── STAGE 0: Exact slug match (highest priority) ──
    # Convert query to slug format and check for direct hit
    slug_query = re.sub(r"[^a-z0-9]+", "-", search_lower).strip("-")
    for r in scraper_results:
        if r["slug"].lower() == slug_query:
            return r["slug"]
    
    # ── STAGE 1: Exact title match (case-insensitive) ──
    for r in scraper_results:
        if r["title"].lower().strip() == search_lower:
            return r["slug"]
    
    # ── STAGE 2: Filter with strict title validation ──
    valid_results = []
    for r in scraper_results:
        if validate_title_match(search_title, r["title"]):
            valid_results.append(r)
    
    if not valid_results:
        return ""
    
    # ── STAGE 2.5: Short-query guard ──
    # For short queries (1-2 words), reject results whose title is vastly longer
    # This prevents "Monster" matching "monogatari-series-off-monster-season"
    is_short_query = len(search_words) <= 2
    if is_short_query:
        strict_results = []
        for r in valid_results:
            title_lower = r["title"].lower().strip()
            title_words = re.findall(r"\w+", title_lower)
            # For short queries, the matched title should not be more than 3x longer in word count
            if len(title_words) <= max(len(search_words) * 3, 4):
                strict_results.append(r)
            # Also accept if the slug is an exact or very close match
            elif r["slug"].lower().replace("-", " ").strip() == search_lower:
                strict_results.append(r)
        if strict_results:
            valid_results = strict_results
    
    # Sort valid results by title length (shorter = purer match)
    sorted_results = sorted(valid_results, key=lambda x: len(x["title"]))
    
    non_tv_keywords = ["movie", "فيلم", "ova", "أوفا", "special", "خاصة", "ونا", "ona", "more"]
    
    # ── STAGE 3: Exact substring containment, prefer non-movie/OVA ──
    for r in sorted_results:
        title_lower = r["title"].lower()
        slug_lower = r["slug"].lower()
        if search_lower in title_lower or title_lower in search_lower:
            if not any(kw in title_lower or kw in slug_lower for kw in non_tv_keywords):
                return r["slug"]
    
    # ── STAGE 4: Substring containment (any type) ──
    for r in sorted_results:
        title_lower = r["title"].lower()
        if search_lower in title_lower or title_lower in search_lower:
            return r["slug"]
    
    # ── STAGE 5: Fallback to best valid result (shortest title) ──
    return sorted_results[0]["slug"]

def sanitize_search_query(title: str) -> str:
    """Cleans the anime title by removing subtitles, special characters, and bullets."""
    if not title:
        return ""
    
    # Replace colons, dashes and slashes with spaces to keep full title keywords
    title = title.replace(":", " ").replace("-", " ").replace("/", " ")
            
    # Remove special bullets like ● and symbols, punctuation
    title = re.sub(r"[●⚫⚪■□◆◇▲▼★☆✦✧♦♣♠♥🃏#@$^*&_+|~`{}[\];\"'<>]", " ", title)
    
    # Replace multiple spaces with a single space
    title = " ".join(title.split())
    return title.strip()
