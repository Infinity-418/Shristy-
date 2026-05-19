import json
import math
import os
import re
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

# Predefined emotional and thematic synonyms for query expansion
SYNONYM_MAP = {
    "exhausted": ["tired", "burnout", "burned out", "fatigue", "drained", "weary"],
    "tired": ["exhausted", "burnout", "burned out", "drained", "sleepy"],
    "burned out": ["exhausted", "tired", "overwhelmed", "stress", "drain"],
    "stressed": ["anxious", "overwhelmed", "pressure", "tense", "worry"],
    "sad": ["down", "depressed", "unhappy", "discouraged", "gloomy"],
    "happy": ["cheerful", "glad", "excited", "joy", "delighted", "content"],
    "coding": ["programming", "developer", "programmer", "software", "codeforces", "dsa"],
    "struggling": ["stuck", "frustrated", "difficult", "hard", "tough", "problem"],
}

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", 
    "to", "of", "in", "on", "at", "for", "with", "about", "against", 
    "during", "before", "after", "above", "below", "from", "up", "down", 
    "out", "off", "over", "under", "again", "further", "then", "once", 
    "here", "there", "when", "where", "why", "how", "all", "any", "both", 
    "each", "few", "more", "most", "other", "some", "such", "no", "nor", 
    "not", "only", "own", "same", "so", "than", "too", "very", "can", 
    "will", "just", "should", "now", "i", "me", "my", "myself", "we", 
    "our", "you", "your", "he", "him", "his", "she", "her", "it", "its"
}


def tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase alphabetic words excluding stopwords."""
    words = re.findall(r'[a-zA-Z0-9]+', text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 1]


class BM25Ranker:
    """Pure Python implementation of BM25 (Okapi BM25) for semantic document retrieval."""
    
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus_size = 0
        self.avgdl = 0.0
        self.doc_lengths = []
        self.doc_freqs: Dict[str, int] = {}
        self.term_freqs: List[Dict[str, int]] = []

    def fit(self, documents: List[str]):
        self.corpus_size = len(documents)
        if self.corpus_size == 0:
            self.avgdl = 0.0
            return

        self.doc_lengths = []
        self.doc_freqs = {}
        self.term_freqs = []

        total_length = 0
        for doc in documents:
            tokens = tokenize(doc)
            length = len(tokens)
            self.doc_lengths.append(length)
            total_length += length

            tf: Dict[str, int] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1
            self.term_freqs.append(tf)

            for t in set(tokens):
                self.doc_freqs[t] = self.doc_freqs.get(t, 0) + 1

        self.avgdl = total_length / self.corpus_size if self.corpus_size > 0 else 0.0

    def score(self, query_tokens: List[str]) -> List[float]:
        if self.corpus_size == 0 or not query_tokens:
            return [0.0] * self.corpus_size

        scores = [0.0] * self.corpus_size
        for token in query_tokens:
            n_q = self.doc_freqs.get(token, 0)
            if n_q == 0:
                continue

            # Standard BM25 IDF formula
            idf = math.log(1.0 + (self.corpus_size - n_q + 0.5) / (n_q + 0.5))

            for doc_idx, tf_dict in enumerate(self.term_freqs):
                freq = tf_dict.get(token, 0)
                if freq == 0:
                    continue
                doc_len = self.doc_lengths[doc_idx]
                denom = freq + self.k1 * (1.0 - self.b + self.b * (doc_len / self.avgdl if self.avgdl > 0 else 1.0))
                numer = freq * (self.k1 + 1.0)
                scores[doc_idx] += idf * (numer / denom)

        return scores


class MemoryManager:
    def __init__(self, filepath: str = "memories.json"):
        self.filepath = filepath
        self.memories: List[Dict[str, Any]] = []
        self.ranker = BM25Ranker()
        self.load_memories()

    def _normalize_memory(self, item: Any) -> Dict[str, Any]:
        """Normalize raw memory string or dict to standard structured schema."""
        if isinstance(item, dict):
            return {
                "id": item.get("id") or f"mem_{uuid.uuid4().hex[:8]}",
                "text": item.get("text") or item.get("fact") or "",
                "category": item.get("category", "general"),
                "confidence": float(item.get("confidence", 1.0)),
                "created_at": item.get("created_at") or datetime.utcnow().isoformat()
            }
        text = str(item).strip()
        category = "general"
        t_lower = text.lower()
        if any(w in t_lower for w in ["name", "is named", "identity", "anubhav"]):
            category = "identity"
        elif any(w in t_lower for w in ["likes", "prefers", "interested", "favorite"]):
            category = "preference"
        elif any(w in t_lower for w in ["goal", "preparing", "trying to", "wants to"]):
            category = "goal"
        elif any(w in t_lower for w in ["feels", "frustrated", "tough", "happy"]):
            category = "state"

        return {
            "id": f"mem_{uuid.uuid4().hex[:8]}",
            "text": text,
            "category": category,
            "confidence": 1.0,
            "created_at": datetime.utcnow().isoformat()
        }

    def load_memories(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    raw_items = data.get("memories", [])
                    self.memories = [self._normalize_memory(item) for item in raw_items if item]
            except Exception as e:
                print(f"Error loading memories: {e}")
                self.memories = []
        else:
            default_facts = [
                "The chatbot companion's name is Shristy.",
                "Shristy is friendly, warm, witty, and deeply cares about the user.",
                "Shristy likes to help the user with coding, brainstorming, and daily chats."
            ]
            self.memories = [self._normalize_memory(f) for f in default_facts]
            self.save_memories()

        self._refresh_ranker()

    def save_memories(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump({"memories": self.memories}, f, indent=4, ensure_ascii=False)
            self._refresh_ranker()
        except Exception as e:
            print(f"Error saving memories: {e}")

    def _refresh_ranker(self):
        docs = [m["text"] for m in self.memories]
        self.ranker.fit(docs)

    def _is_duplicate(self, text: str, threshold: float = 0.8) -> bool:
        """Check for exact or high-Jaccard token similarity with existing memories."""
        t_clean = text.lower().strip()
        tokens = set(tokenize(t_clean))
        if not tokens:
            return False

        for mem in self.memories:
            existing_clean = mem["text"].lower().strip()
            if t_clean == existing_clean:
                return True
            existing_tokens = set(tokenize(existing_clean))
            if existing_tokens:
                intersection = tokens.intersection(existing_tokens)
                union = tokens.union(existing_tokens)
                if len(intersection) / len(union) >= threshold:
                    return True
        return False

    def add_memory(self, fact: str, category: str = "general", confidence: float = 1.0) -> Optional[Dict[str, Any]]:
        """Add a validated fact with deduplication and schema normalization."""
        if not fact or not isinstance(fact, str):
            return None
        fact = fact.strip()
        if len(fact) < 5 or self._is_duplicate(fact):
            return None

        mem_obj = {
            "id": f"mem_{uuid.uuid4().hex[:8]}",
            "text": fact,
            "category": category,
            "confidence": round(confidence, 2),
            "created_at": datetime.utcnow().isoformat()
        }
        self.memories.append(mem_obj)
        self.save_memories()
        return mem_obj

    def delete_memory(self, memory_id_or_text: str) -> bool:
        """Delete an individual memory by ID or exact text match."""
        initial_len = len(self.memories)
        self.memories = [
            m for m in self.memories 
            if m["id"] != memory_id_or_text and m["text"].strip() != memory_id_or_text.strip()
        ]
        if len(self.memories) < initial_len:
            self.save_memories()
            return True
        return False

    def clear_memories(self):
        """Clear all stored memories."""
        self.memories = []
        self.save_memories()

    def get_all_memories(self) -> List[Dict[str, Any]]:
        """Return all memories formatted as structured records."""
        return self.memories

    def get_relevant_memories(self, query: str, limit: int = 5) -> List[str]:
        """
        BM25 retrieval enhanced with query synonym expansion.
        Handles semantically related queries (e.g., 'exhausted' matches 'burned out').
        """
        if not self.memories:
            return []
        if not query:
            return [m["text"] for m in self.memories[:limit]]

        tokens = tokenize(query)
        # Expand tokens with emotional and contextual synonyms
        expanded_tokens = list(tokens)
        query_lower = query.lower()
        for phrase, synonyms in SYNONYM_MAP.items():
            if phrase in query_lower:
                expanded_tokens.extend(synonyms)

        scores = self.ranker.score(expanded_tokens)

        # Pair scores with memory items
        scored_pairs = list(zip(scores, self.memories))
        scored_pairs.sort(key=lambda x: x[0], reverse=True)

        results = [m["text"] for score, m in scored_pairs if score > 0.1]

        # Fill remaining quota with latest memories if needed
        if len(results) < limit:
            for m in reversed(self.memories):
                if m["text"] not in results:
                    results.append(m["text"])
                if len(results) >= limit:
                    break

        return results[:limit]

    def get_contextual_memories(self, query: str = "", limit: int = 10) -> List[str]:
        """
        Construct balanced context combining:
        1. Core identity and preferences
        2. High-relevance BM25 matches for current query
        3. Recent interaction state
        """
        if not self.memories:
            return []

        selected: List[str] = []
        seen = set()

        def add_entry(text: str):
            if text and text not in seen:
                seen.add(text)
                selected.append(text)

        # 1. Identity & profile facts (up to 3)
        identity_memories = [m["text"] for m in self.memories if m.get("category") == "identity"]
        for m in identity_memories[:3]:
            add_entry(m)

        # 2. BM25 relevant memories for the prompt
        if query:
            bm25_matches = self.get_relevant_memories(query, limit=limit)
            for m in bm25_matches:
                add_entry(m)

        # 3. Recent interaction memories (last 4)
        for m in reversed(self.memories[-4:]):
            add_entry(m["text"])

        # 4. Fill remaining limit if needed
        if len(selected) < limit:
            for m in reversed(self.memories):
                add_entry(m["text"])
                if len(selected) >= limit:
                    break

        return selected[:limit]
