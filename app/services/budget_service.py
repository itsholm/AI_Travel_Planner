from models.schemas import Budget, TripPlan


def calculate_budget(plan: TripPlan) -> Budget:
    """Build a budget snapshot from the current plan contents."""
    attractions_total = sum(
        attraction.ticket_price
        for day in plan.days
        for attraction in day.attractions
    )
    hotels_total = sum(day.hotel.estimated_cost for day in plan.days if day.hotel)
    meals_total = sum(
        meal.estimated_cost
        for day in plan.days
        for meal in day.meals
    )

    # Transportation is still a fixed estimate tied to trip length.
    transportation_total = 50.0 * plan.travel_days

    return Budget(
        total_attractions=int(attractions_total),
        total_hotels=int(hotels_total),
        total_meals=int(meals_total),
        total_transportation=int(transportation_total),
        total=int(attractions_total + hotels_total + meals_total + transportation_total),
    )
