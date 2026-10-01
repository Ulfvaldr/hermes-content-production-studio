from pprint import pprint

from src.agents.bao import Bao
from src.schemas.request import ContentRequest


request = ContentRequest(
    topic="Portable power station for camping and emergency home use",
    target_audience="Campers and homeowners",
    objective="Create a 60-second promotional video",
    duration="60 seconds",
    production_type="Hybrid",
    platform="Instagram Reels",
    tone="Practical and trustworthy",
)

bao = Bao()
result = bao.research(request)

pprint(result)