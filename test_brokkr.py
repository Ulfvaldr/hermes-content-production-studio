from pprint import pprint

from src.agents.bao import Bao
from src.agents.brokkr import Brokkr
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

print("Running Bao research...")

bao = Bao()
research = bao.research(request)

print("Bao complete.")
print("Running Brokkr production build...")

brokkr = Brokkr()
production_pack = brokkr.build(
    request=request,
    research=research,
)

print("Brokkr complete.")

pprint(production_pack)