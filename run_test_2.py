from pprint import pprint

from src.schemas.request import ContentRequest
from src.workflows.content_production import ContentProductionWorkflow


def main():
    request = ContentRequest(
        topic="How AI agents work and how they can help small businesses",
        target_audience="General audience and small business owners with little AI experience",
        objective=(
            "Create an educational YouTube video that clearly explains "
            "AI agents, gives practical examples, and avoids unnecessary jargon"
        ),
        duration="5-8 minutes",
        production_type="Hybrid",
        platform="YouTube",
        tone="Clear, practical, trustworthy, and beginner-friendly",
        notes=(
            "Explain the difference between a normal chatbot and an AI agent. "
            "Include realistic small-business examples. Avoid exaggerated claims "
            "about autonomy or replacing employees."
        ),
    )

    workflow = ContentProductionWorkflow(max_revisions=1)

    result = workflow.run(request)

    print("\n=== TEST CASE 2 FINAL PRODUCTION PACK ===\n")
    pprint(result)


if __name__ == "__main__":
    main()