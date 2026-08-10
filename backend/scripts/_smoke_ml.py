from app.services.ml.pricing_engine import pricing_engine

result = pricing_engine.predict(
    composite_score=75,
    city_music_score=90,
    venue_capacity=15000,
    proposed_price=3500,
    category="music",
    is_international=False,
    lead_days=45,
)
print("=== ML Pricing Smoke Test ===")
print("  Model:             ", result["model"])
print("  Proposed price:     Rs.3,500")
print("  Recommended price:  Rs.", int(result["recommended_price"]))
print("  Predicted fill:    ", result["predicted_fill_rate"], "%")
print("  Confidence:        ", result["confidence"], "%")
print("  Sensitivity pts:   ", len(result["sensitivity_curve"]))

r2 = pricing_engine.predict(
    composite_score=88,
    city_music_score=95,
    venue_capacity=30000,
    proposed_price=6000,
    category="music",
    is_international=True,
    lead_days=90,
)
print("\n=== International Act ===")
print("  Rs.6,000 -> Recommended Rs.", int(r2["recommended_price"]), "| Fill:", r2["predicted_fill_rate"], "%")
print("\nPASS")
