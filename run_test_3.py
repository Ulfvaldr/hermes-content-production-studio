from pprint import pprint

from src.schemas.request import ContentRequest
from src.workflows.content_production import ContentProductionWorkflow


def main():
    request = ContentRequest(
        topic=(
            "A cinematic short about a lone traveler discovering an abandoned "
            "research station in a frozen landscape"
        ),
        target_audience=(
            "Viewers who enjoy cinematic sci-fi, mystery, and atmospheric short-form storytelling"
        ),
        objective=(
            "Create a 60-90 second cinematic short designed primarily for AI-generated video, "
            "with strong visual continuity, clear scene progression, and production-ready prompts"
        ),
        duration="60-90 seconds",
        production_type="AI-generated",
        platform="YouTube Shorts / Instagram Reels",
        tone="Cinematic, mysterious, atmospheric, grounded, and visually consistent",
        notes=(
            "Use one recurring traveler character and one recurring frozen research station. "
            "Prioritize continuity of clothing, environment, lighting, props, camera style, "
            "and geography between scenes. Avoid changing the character's face, outfit, or "
            "the station layout between shots. Include a practical generation sequence so "
            "the creator knows which reference images or keyframes to generate first."
        ),
    )

    workflow = ContentProductionWorkflow(max_revisions=1)

    result = workflow.run(request)

    print("\n=== TEST CASE 3 FINAL PRODUCTION PACK ===\n")
    pprint(result)


if __name__ == "__main__":
    main()