from typing import Any, Dict


class MockBusinessTravelTool:
    def __init__(self, name: str, description: str, input_schema: Dict[str, Any], handler):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self._handler = handler

    def to_dict(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }

    async def run(self, **kwargs):
        return self._handler(**kwargs)


def _object_schema(properties: Dict[str, Any], required=None) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
    }


def create_business_travel_tools():
    return [
        MockBusinessTravelTool(
            "get_travel_policy",
            "读取公司差旅政策和员工等级对应标准。",
            _object_schema(
                {
                    "employee_level": {"type": "string"},
                    "destination_city": {"type": "string"},
                },
                ["employee_level", "destination_city"],
            ),
            lambda employee_level, destination_city: {
                "employee_level": employee_level,
                "destination_city": destination_city,
                "hotel_budget_per_night": 700 if employee_level == "standard" else 1000,
                "transport_policy": "优先高铁；航班需避免红眼航班。",
                "hotel_policy": "优先选择可取消、会议地点3公里内酒店。",
            },
        ),
        MockBusinessTravelTool(
            "search_train",
            "查询企业差旅可选高铁或火车方案。",
            _object_schema(
                {
                    "origin_city": {"type": "string"},
                    "destination_city": {"type": "string"},
                    "date": {"type": "string"},
                },
                ["origin_city", "destination_city", "date"],
            ),
            lambda origin_city, destination_city, date: {
                "options": [
                    {
                        "train_no": "G7317",
                        "origin": origin_city,
                        "destination": destination_city,
                        "date": date,
                        "depart_time": "09:05",
                        "arrive_time": "10:12",
                        "cost": 120,
                    }
                ]
            },
        ),
        MockBusinessTravelTool(
            "search_hotel",
            "查询符合公司差旅标准的酒店。",
            _object_schema(
                {
                    "city": {"type": "string"},
                    "meeting_location": {"type": "string"},
                    "max_distance_km": {"type": "number"},
                    "refundable_required": {"type": "boolean"},
                    "max_price": {"type": "integer"},
                },
                ["city", "meeting_location", "max_distance_km", "refundable_required", "max_price"],
            ),
            lambda city, meeting_location, max_distance_km, refundable_required, max_price: {
                "hotels": [
                    {
                        "hotel_id": "hotel-hz-binjiang-001",
                        "name": f"{city}滨江商务酒店",
                        "address": f"{meeting_location}附近",
                        "distance_km": min(max_distance_km, 2.4),
                        "refundable": refundable_required,
                        "cost_per_night": min(max_price, 668),
                    }
                ]
            },
        ),
        MockBusinessTravelTool(
            "check_budget",
            "校验候选交通和酒店方案是否满足预算。",
            _object_schema(
                {
                    "budget_limit": {"type": "integer"},
                    "transport_cost": {"type": "integer"},
                    "hotel_cost": {"type": "integer"},
                    "other_cost": {"type": "integer"},
                },
                ["budget_limit", "transport_cost", "hotel_cost", "other_cost"],
            ),
            lambda budget_limit, transport_cost, hotel_cost, other_cost: {
                "budget_limit": budget_limit,
                "estimated_total": transport_cost + hotel_cost + other_cost,
                "passed": transport_cost + hotel_cost + other_cost <= budget_limit,
            },
        ),
        MockBusinessTravelTool(
            "book_hotel",
            "预订酒店，会产生外部副作用。",
            _object_schema(
                {
                    "hotel_id": {"type": "string"},
                    "guest_names": {"type": "array", "items": {"type": "string"}},
                    "check_in": {"type": "string"},
                    "check_out": {"type": "string"},
                    "idempotency_key": {"type": "string"},
                },
                ["hotel_id", "guest_names", "check_in", "check_out", "idempotency_key"],
            ),
            lambda hotel_id, guest_names, check_in, check_out, idempotency_key: {
                "booking_id": f"BK-{idempotency_key[-8:]}",
                "hotel_id": hotel_id,
                "guest_names": guest_names,
                "check_in": check_in,
                "check_out": check_out,
                "status": "CONFIRMED",
            },
        ),
        MockBusinessTravelTool(
            "calendar_create",
            "写入差旅行程到日历。",
            _object_schema(
                {
                    "title": {"type": "string"},
                    "date": {"type": "string"},
                    "location": {"type": "string"},
                },
                ["title", "date", "location"],
            ),
            lambda title, date, location: {
                "calendar_event_id": f"cal-{date}",
                "title": title,
                "date": date,
                "location": location,
                "status": "CREATED",
            },
        ),
        MockBusinessTravelTool(
            "send_itinerary",
            "发送行程通知邮件。",
            _object_schema(
                {
                    "emails": {"type": "array", "items": {"type": "string"}},
                    "summary": {"type": "string"},
                },
                ["emails", "summary"],
            ),
            lambda emails, summary: {
                "message_id": "msg-demo-itinerary",
                "sent_to": emails,
                "summary": summary,
                "status": "SENT",
            },
        ),
    ]
