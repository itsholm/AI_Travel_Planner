/**
 * 对应 schemas.py 中的 Location 模型
 * 用于高德地图精确渲染
 */
export interface Location {
  latitude: number;
  longitude: number;
}

/**
 * 对应 schemas.py 中的 Attraction 模型
 */
export interface Attraction {
  name: string
  address: string
  location: Location
  visit_duration: number
  description: string
  category?: string
  ticket_price?: number
}

/**
 * 对应 schemas.py 中的 Meal 模型
 */
export interface Meal {
  type:'breakfast' | 'lunch' | 'dinner' | 'snack'// "早餐" | "午餐" | "晚餐"
  name: string;
  address?:string;
  location?:Location
  description?: string;
  estimated_cost?:number
}

/**
 * 对应 schemas.py 中的 Hotel 模型
 */
export interface Hotel {
  name: string
  address: string
  location?: Location
  price_range: string
  rating: string
  distance: string
  type: string
  estimated_cost?: number
}

/**
 * 对应 schemas.py 中的 WeatherInfo 模型
 */
export interface WeatherInfo {
  date: string;
  day_weather: string;
  night_weather: string;
  day_temp: number;
  night_temp: number;
  wind_direction?: string;
  wind_power?: string;
}

export interface Budget {
  total_attractions: number
  total_hotels: number
  total_meals: number
  total_transportation: number
  total: number
}
/**
 * 对应 schemas.py 中的 DayPlan 模型
 */
export interface DayPlan {
  day_index: number; // 对应后端的 day_index
  date: string;
  weather: string;
  description: string
  transportation: string
  accommodation: string
  hotel?: Hotel; // 每一天可能有推荐酒店
  attractions: Attraction[]; // 对应后端的 attractions
  meals: Meal[]; // 对应后端的 meals 列表
}

/**
 * 整个旅行计划的结构
 * 对应后端 TripPlan 类
 */
export interface TravelPlan {
  task_id?: string;
  session_id?: string;
  city: string;
  start_date: string;
  end_date: string;
  travel_days: number;
  overall_suggestions: string;
  weather_info: WeatherInfo[]; // 后端返回的完整天气预报列表
  days: DayPlan[];
  budget?:Budget
}

export interface TripPlanResponse {
  success: boolean
  message: string
  data?: TravelPlan
}