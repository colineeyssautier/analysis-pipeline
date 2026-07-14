"""
03_generate_report.py
======================
Interactive tool: ask any question about project viability,
risks, or patterns, based on Square of Youth's past projects
and any reference documents added to the system.

Installation:
    pip install groq

Environment variable to add to your existing .env:
    GROQ_API_KEY=your_groq_key
"""

from retrieval import ask


def interactive_loop():
    print("=" * 60)
    print("Square of Youth — Project Analysis Assistant")
    print("=" * 60)
    print("Ask anything about project viability, risks, or patterns.")
    print("You can write your question in any language, and include")
    print("as much project detail as you want. Type 'exit' to quit.\n")

    while True:
        question = input("Your question:\n> ").strip()
        if question.lower() in ("exit", "quit", "q"):
            print("Goodbye.")
            break
        if not question:
            continue

        answer, subqueries, projects, documents = ask(question)

        print(f"\n{len(projects)} relevant projects found, {len(documents)} relevant reference documents found")
        if len(subqueries) > 1:
            print("Angles explored:")
            for sq in subqueries:
                print(f"  - {sq}")
        print("\n" + "=" * 60)
        print("ANALYSIS")
        print("=" * 60)
        print(answer)
        print("\n")


if __name__ == "__main__":
    interactive_loop()