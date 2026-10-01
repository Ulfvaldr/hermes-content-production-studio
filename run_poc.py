from pprint import pprint

from src.schemas.request import ContentRequest
from src.workflows.content_production import ContentProductionWorkflow


def main():
    request = ContentRequest(
        topic="Portable power station for camping and emergency home use",
        target_audience="Campers and homeowners",
        objective="Create a 60-second promotional video",
        duration="60 seconds",
        production_type="Hybrid",
        platform="Instagram Reels",
        tone="Practical and trustworthy",
    )

    workflow = ContentProductionWorkflow()
    result = workflow.run(request)

    pprint(result)


if __name__ == "__main__":
    main()