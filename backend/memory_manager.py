import json
import os
import re

class MemoryManager:
    def __init__(self, filepath="memories.json"):
        self.filepath = filepath
        self.memories = []
        self.load_memories()

    def load_memories(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.memories = data.get("memories", [])
            except Exception as e:
                print(f"Error loading memories: {e}")
                self.memories = []
        else:
            self.memories = [
                "The chatbot companion's name is Shristy.",
                "Shristy is friendly, warm, witty, and deeply cares about the user.",
                "Shristy likes to help the user with coding, brain-storming, and daily chats."
            ]
            self.save_memories()

    def save_memories(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump({"memories": self.memories}, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving memories: {e}")

    def add_memory(self, fact):
        if not fact or not isinstance(fact, str):
            return
        fact = fact.strip()
        if fact and fact not in self.memories:
            self.memories.append(fact)
            self.save_memories()

    def get_relevant_memories(self, query, limit=3):
        if not query:
            return self.memories[:limit]
        
        # Simple TF-IDF / keyword similarity search in pure Python
        # Tokenize query
        words = re.findall(r'\w+', query.lower())
        stopwords = {
            "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", 
            "to", "of", "in", "on", "at", "for", "with", "about", "against", 
            "during", "before", "after", "above", "below", "to", "from", 
            "up", "down", "in", "out", "on", "off", "over", "under", "again", 
            "further", "then", "once", "here", "there", "when", "where", "why", 
            "how", "all", "any", "both", "each", "few", "more", "most", "other", 
            "some", "such", "no", "nor", "not", "only", "own", "same", "so", 
            "than", "too", "very", "s", "t", "can", "will", "just", "don", "should", "now"
        }
        query_tokens = [w for w in words if w not in stopwords]
        
        if not query_tokens:
            return self.memories[:limit]
        
        scored_memories = []
        for memory in self.memories:
            memory_lower = memory.lower()
            score = 0
            for token in query_tokens:
                # Direct word matches
                matches = len(re.findall(r'\b' + re.escape(token) + r'\b', memory_lower))
                score += matches * 2
                # Substring match fallback
                if token in memory_lower and matches == 0:
                    score += 0.5
            
            scored_memories.append((score, memory))
        
        # Sort by score descending, then return top items
        scored_memories.sort(key=lambda x: x[0], reverse=True)
        
        # Filter memories with a positive score first, if possible
        results = [mem for score, mem in scored_memories if score > 0]
        if len(results) < limit:
            # Pad with latest memories if not enough query matches
            for mem in reversed(self.memories):
                if mem not in results:
                    results.append(mem)
                if len(results) >= limit:
                    break
                    
        return results[:limit]

    def get_contextual_memories(self, query: str = "", limit: int = 12):
        if not self.memories:
            return []

        selected = []
        seen = set()

        def add_fact(f):
            if f and f not in seen:
                seen.add(f)
                selected.append(f)

        # 1. Core Profile facts (Identity, background, habits)
        for mem in self.memories:
            m_lower = mem.lower()
            if any(k in m_lower for k in ["user is anubhav", "named anubhav", "anubhav."]):
                add_fact(mem)
                break

        for mem in self.memories:
            m_lower = mem.lower()
            if any(k in m_lower for k in ["codeforces", "programmer", "computer science", "dsa"]):
                add_fact(mem)
                if len(selected) >= 3:
                    break

        # 2. Recent context from earlier/latest interactions (last 5 memories)
        for mem in reversed(self.memories[-5:]):
            add_fact(mem)

        # 3. Query-specific relevance matching
        if query:
            relevant = self.get_relevant_memories(query, limit=limit)
            for mem in relevant:
                add_fact(mem)

        # 4. Fill remaining capacity with recent memories
        if len(selected) < limit:
            for mem in reversed(self.memories):
                add_fact(mem)
                if len(selected) >= limit:
                    break

        return selected[:limit]
