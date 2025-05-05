from dotenv import load_dotenv
from langchain_tavily import TavilySearch
import os
import httpx
from mcp.server.fastmcp import FastMCP
from typing import Optional, Literal, List


load_dotenv()

weather_key = os.getenv('WEATHER_API_KEY')
tavily_key = os.getenv('TAVILY_API_KEY')
amadeus_secret = os.getenv('AMADEUS_API_SECRET')
amadeus_api = os.getenv('AMADEUS_API_KEY')

# Initialize MCP
mcp = FastMCP('travel_server')

## Functions to use

def format_answer(url_response):
    '''
    Function to format the answer from the request with the needed weather information.
    '''
    # Location info
    location = url_response['location']
    place_info = {
    'name': location['name'],
    'region': location['region'],
    'country': location['country']
    }

    # Formatting answer
    forecasts = []
    for day in url_response['forecast']['forecastday']:
        daily_info = {
            **place_info,
            'date': day['date'],
            'temp_c': day['day']['avgtemp_c'],
            'condition': day['day']['condition']['text'],
            'precip_mm': day['day']['totalprecip_mm'],
            'humidity': day['day']['avghumidity'],
            'feelslike_c': day['day'].get('feelslike_c', day['day']['avgtemp_c'])
        }
        forecasts.append(daily_info)
    return forecasts

async def make_amadeus_request():
    '''
    Function to obtain the access token to Amadeus API services
    '''
    async with httpx.AsyncClient() as client:
        auth_response = await client.post(
        'https://test.api.amadeus.com/v1/security/oauth2/token',
        data={
            'grant_type': 'client_credentials',
            'client_id': amadeus_api,
            'client_secret': amadeus_secret
        }
        )
        return auth_response.json()['access_token']


def format_hotels_answer(hotels):
    result_hotels = []
    for hotel in hotels['data']:
        hotels_dict = {}
        hotels_dict['hotel_name'] = hotel['name']
        hotels_dict['distance_from_center_in_km'] = hotel['distance']['value']
        result_hotels.append(hotels_dict)
    return result_hotels

def format_flight_answer(response_json):
    segments_info = []
    final_dict = {}

    flight_offer = response_json['data'][0]
    itineraries = flight_offer['itineraries']

    for itinerary in itineraries:
        for segment in itinerary['segments']:
            segment_data = {
                'departure_airport': segment['departure']['iataCode'],
                'departure_time': segment['departure']['at'],
                'arrival_airport': segment['arrival']['iataCode'],
                'arrival_time': segment['arrival']['at'],
                'flight_number': f"{segment['carrierCode']} {segment['number']}",
                'duration': segment['duration'],
                'number_of_stops': segment['numberOfStops']
            }
            segments_info.append(segment_data)
    
    final_dict['travel_steps'] = segments_info
    final_dict['price_in_euro'] = flight_offer['price']['total']
    return [final_dict]


# Creating the MCP tools

## Weather Info
@mcp.tool()
async def get_weather_info(city: str, number_of_days: Literal[1,2,3,4]) -> list:
    '''
    Function to request weather info and formatting it.

    Args:
        city: name of the city to search for
        number_of_days: number of days of the forecasts. One if only for one day. The maximum number is 4 days in the future.
    '''
    async with httpx.AsyncClient() as client:
        try:
            url_response = await client.get(f"https://api.weatherapi.com/v1/forecast.json?key={weather_key}&q={city}&days={number_of_days}")
            weather_answer = url_response.json()
            return format_answer(weather_answer)
        except Exception:
            return None
        
## Latest News
@mcp.tool()
async def get_recent_news(query: str) -> list:
    '''
    Function to get the most relevant news for a place. This is specific for tourists.
    
    Args:
        query: the news to search over the internet
    '''
    tavily_search_tool = TavilySearch(
        max_results=5,
        topic='news',
        search_depth='advanced'
        )    
    news = await tavily_search_tool.ainvoke(query)
    return news['results']


## Hotels
@mcp.tool()
async def get_hotels(city: str, km_from_center: int, amenities: Optional[List[Literal[
        "SWIMMING_POOL", "SPA", "FITNESS_CENTER", "AIR_CONDITIONING", "RESTAURANT",
        "PARKING", "PETS_ALLOWED", "AIRPORT_SHUTTLE", "BUSINESS_CENTER", "DISABLED_FACILITIES",
        "WIFI", "MEETING_ROOMS", "NO_KID_ALLOWED", "TENNIS", "GOLF", "KITCHEN",
        "ANIMAL_WATCHING", "BABY-SITTING", "BEACH", "CASINO", "JACUZZI", "SAUNA",
        "SOLARIUM", "MASSAGE", "VALET_PARKING", "BAR or LOUNGE", "KIDS_WELCOME",
        "NO_PORN_FILMS", "MINIBAR", "TELEVISION", "WI-FI_IN_ROOM", "ROOM_SERVICE",
        "GUARDED_PARKG", "SERV_SPEC_MENU"]]]=None, ratings: Optional[List[Literal["1", "2", "3", "4", "5"]]]=None) -> list:
    '''
    Function to search for hotels through Amadeus API.
    It returns the hotels names.
    Args:
        city: IATA code of the city. For example ROM (Rome), PAR (Paris). It must be a string.
        km_from_center: radius from the center in kms. It must be an integer.
        amenities: list of amenities as strings. These are the possible ones:
                    "SWIMMING_POOL", "SPA", "FITNESS_CENTER", "AIR_CONDITIONING", "RESTAURANT",
                    "PARKING", "PETS_ALLOWED", "AIRPORT_SHUTTLE", "BUSINESS_CENTER", "DISABLED_FACILITIES",
                    "WIFI", "MEETING_ROOMS", "NO_KID_ALLOWED", "TENNIS", "GOLF", "KITCHEN",
                    "ANIMAL_WATCHING", "BABY-SITTING", "BEACH", "CASINO", "JACUZZI", "SAUNA",
                    "SOLARIUM", "MASSAGE", "VALET_PARKING", "BAR or LOUNGE", "KIDS_WELCOME",
                    "NO_PORN_FILMS", "MINIBAR", "TELEVISION", "WI-FI_IN_ROOM", "ROOM_SERVICE",
                    "GUARDED_PARKG", "SERV_SPEC_MENU". Example: ['PARKING']
        ratings: list of possible ratings in a string format. List of possible values: ['1','2','3','4','5']
    '''
    #Getting the token
    request_token = await make_amadeus_request()
    headers = {
    'Authorization': f'Bearer {request_token}'
            }
    
    # Params to put in the request
    params = {
    'cityCode': city, 
    'radius':km_from_center,
    'radiusUnit':'KM',
    'amenities':amenities,
    'ratings':ratings
    }

    params_to_pass = {}
    
    for k,v in params.items():
        if v is not None:
            params_to_pass[k] = v

    # Getting response
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
            'https://test.api.amadeus.com/v1/reference-data/locations/hotels/by-city',
            headers=headers,
            params=params_to_pass
            )
            hotels = response.json()
            return format_hotels_answer(hotels)
        except Exception:
            return None  
        
## Flights
@mcp.tool()
async def get_flights(origin: str, destination: str, departure_date: str, adults: int, return_date: Optional[str]=None) -> list:
    '''
    Find flights from a given source to a destination giving back prices.
    It is used only if the user specifies that it wants information about flights.
    
    Args:
        origin: origin of the flight. It uses IATA code (e.g. ROM, PAR).
        destination: destination of the flight. It uses IATA code (e.g. ROM, PAR).
        departure_date: departure date as a string in format "yyyy-mm-dd".
        return_date: return date as a string in format "yyyy-mm-dd". It is nullable, so the user cannot provide it.
        adults: number of adults to book for. It must be an integer of minimum 1.
    '''
    # Requesting token
    request_token = await make_amadeus_request()
    print(request_token)
    headers = {
        'Authorization': f'Bearer {request_token}'
    }

    params = {
        'originLocationCode': origin,
        'destinationLocationCode':destination,
        'departureDate':departure_date,
        'returnDate':return_date,
        'adults':adults,
        'nonStop':'false',
        'max':1
    }

    params_to_pass = {}
    
    for k,v in params.items():
        if v is not None:
            params_to_pass[k] = v
    
    # Getting response
    async with httpx.AsyncClient() as flight_client:
        try:
            flight_response = await flight_client.get(
                'https://test.api.amadeus.com/v2/shopping/flight-offers',
                headers=headers,
                params=params_to_pass
            )
            flights = flight_response.json()
            return format_flight_answer(flights)
        except Exception:
            return None

if __name__ == '__main__':
    mcp.run()