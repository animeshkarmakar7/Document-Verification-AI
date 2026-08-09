from app.services.gemini_classifier import GeminiClassifier

classifier = GeminiClassifier()
clauses = [
    {"clause_id": "doc-1-clause-0001", "heading": "Termination", "text": "Landlord may terminate this lease at any time."},
    {"clause_id": "doc-1-clause-0002", "heading": "Late Fee", "text": "Tenant shall pay 10% penalty for late rent."},
]

try:
    results = classifier.classify_batch(clauses)
    print("CLASSIFICATION SUCCESS:", len(results))
    for r in results:
        print(r.clause_id, "->", r.category)
except Exception as e:
    print("CLASSIFICATION ERROR:", type(e).__name__, ":", e)
