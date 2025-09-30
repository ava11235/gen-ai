import json
import boto3
import urllib.request
import urllib.parse

def lambda_handler(event, context):
    """Weather agent with forecast and clothing advice"""
    
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Allow-Methods': 'POST, OPTIONS'
    }
    
    try:
        if 'body' in event:
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
        else:
            body = event
            
        message = body.get('message', 'No message')
        
        # Check if it's a weather query
        weather_keywords = ['weather', 'temperature', 'temp', 'rain', 'sunny', 'cloudy', 'forecast', 'wear', 'clothing', 'dress']
        is_weather_query = any(keyword in message.lower() for keyword in weather_keywords)
        
        if is_weather_query:
            city = extract_and_fix_city(message)
            
            # Check if user wants forecast or clothing advice
            forecast_keywords = ['forecast', 'tomorrow', 'next', 'days', 'week', 'future']
            clothing_keywords = ['wear', 'clothing', 'dress', 'outfit', 'should i']
            
            wants_forecast = any(keyword in message.lower() for keyword in forecast_keywords)
            wants_clothing_advice = any(keyword in message.lower() for keyword in clothing_keywords)
            
            if wants_forecast:
                weather_result = get_weather_forecast(city, include_clothing=wants_clothing_advice)
            else:
                weather_result = get_current_weather(city, include_clothing=wants_clothing_advice)
            
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({'response': weather_result, 'success': True})
            }
        
        # Non-weather: use Bedrock
        bedrock = boto3.client('bedrock-runtime', region_name='us-west-2')
        
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 500,
            "messages": [{"role": "user", "content": message}]
        }
        
        response = bedrock.invoke_model(
            modelId="anthropic.claude-3-5-sonnet-20241022-v2:0",
            body=json.dumps(request_body)
        )
        
        response_body = json.loads(response['body'].read())
        claude_response = response_body['content'][0]['text']
        
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({'response': claude_response, 'success': True})
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error': f"Error: {str(e)}", 'success': False})
        }

def get_clothing_recommendation(temp_c, condition, is_rainy=False):
    """Generate clothing recommendations based on temperature and conditions"""
    
    # Temperature-based recommendations
    if temp_c >= 25:  # 77°F+
        base_clothing = "👕 Light clothing: T-shirt, shorts, sandals"
    elif temp_c >= 20:  # 68°F+
        base_clothing = "👔 Comfortable clothing: Light shirt, pants, sneakers"
    elif temp_c >= 15:  # 59°F+
        base_clothing = "🧥 Light layers: Long sleeves, light jacket, pants"
    elif temp_c >= 10:  # 50°F+
        base_clothing = "🧥 Warm layers: Sweater or hoodie, jacket, long pants"
    elif temp_c >= 5:   # 41°F+
        base_clothing = "🧥 Winter clothing: Warm coat, layers, gloves"
    else:  # Below 41°F
        base_clothing = "❄️ Heavy winter gear: Heavy coat, hat, gloves, warm boots"
    
    # Weather condition additions
    additions = []
    
    if is_rainy or 'rain' in condition.lower() or 'drizzle' in condition.lower() or 'showers' in condition.lower():
        additions.append("☔ Umbrella or rain jacket")
    
    if 'snow' in condition.lower():
        additions.append("❄️ Waterproof boots, extra layers")
    
    if 'wind' in condition.lower() or temp_c < 10:
        additions.append("🌬️ Windbreaker or scarf")
    
    if 'sunny' in condition.lower() or 'clear' in condition.lower():
        additions.append("🕶️ Sunglasses, sunscreen")
    
    # Combine recommendations
    recommendation = base_clothing
    if additions:
        recommendation += "\n👗 **Also bring:** " + ", ".join(additions)
    
    return recommendation

def extract_and_fix_city(message):
    """Extract city and fix common US state abbreviation issues"""
    
    # Simple extraction
    words = message.lower().replace('?', '').replace('.', '').split()
    
    # Look for "in [city]" or "for [city]" pattern
    city = "Seattle"  # default
    for i, word in enumerate(words):
        if word in ['in', 'for'] and i + 1 < len(words):
            # Take everything after "in"/"for"
            city_parts = words[i+1:]
            city = ' '.join(city_parts).title()
            break
    
    # Fix common US state abbreviation patterns
    city = fix_us_states(city)
    
    return city

def fix_us_states(city_text):
    """Fix US state abbreviations to proper format"""
    
    # Common US state abbreviations that cause geocoding issues
    state_fixes = {
        ' Wa': ', WA', ' Ca': ', CA', ' Ny': ', NY', ' Tx': ', TX', ' Fl': ', FL',
        ' Il': ', IL', ' Pa': ', PA', ' Oh': ', OH', ' Mi': ', MI', ' Ga': ', GA'
    }
    
    # Apply fixes
    for bad_format, good_format in state_fixes.items():
        if city_text.endswith(bad_format):
            city_text = city_text.replace(bad_format, good_format)
            break
    
    # If no state, try just the city name
    if ',' not in city_text and len(city_text.split()) > 1:
        words = city_text.split()
        if len(words) == 2 and len(words[1]) == 2:  # Likely a state abbreviation
            return words[0]  # Just return the city name
    
    return city_text

def get_current_weather(city, include_clothing=False):
    """Get current weather data with optional clothing advice"""
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(city)}&count=1&language=en&format=json"
        
        with urllib.request.urlopen(geo_url, timeout=10) as response:
            geo_data = json.loads(response.read().decode())
        
        if not geo_data.get('results'):
            if ' ' in city:
                city_only = city.split()[0]
                geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(city_only)}&count=1&language=en&format=json"
                
                with urllib.request.urlopen(geo_url, timeout=10) as response:
                    geo_data = json.loads(response.read().decode())
                
                if not geo_data.get('results'):
                    return f"❌ Could not find weather for '{city}'. Try just the city name."
            else:
                return f"❌ Could not find weather for '{city}'. Please check the spelling."
        
        result = geo_data['results'][0]
        lat = result['latitude']
        lon = result['longitude']
        city_name = result['name']
        country = result.get('country', 'Unknown')
        
        # Get current weather
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code&timezone=auto"
        
        with urllib.request.urlopen(weather_url, timeout=10) as response:
            weather_data = json.loads(response.read().decode())
        
        current = weather_data['current']
        temp_c = round(current['temperature_2m'], 1)
        temp_f = round((temp_c * 9/5) + 32, 1)
        humidity = current['relative_humidity_2m']
        wind = round(current['wind_speed_10m'], 1)
        code = current['weather_code']
        
        conditions = {
            0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
            45: "Fog", 51: "Light drizzle", 61: "Slight rain", 63: "Moderate rain",
            65: "Heavy rain", 71: "Slight snow", 80: "Rain showers", 95: "Thunderstorm"
        }
        condition = conditions.get(code, "Unknown conditions")
        
        response_text = f"""🌤️ **Current Weather in {city_name}, {country}**

🌡️ **Temperature:** {temp_c}°C ({temp_f}°F)
💧 **Humidity:** {humidity}%
🌬️ **Wind Speed:** {wind} km/h
☁️ **Conditions:** {condition}"""

        # Add clothing recommendation if requested
        if include_clothing:
            is_rainy = code in [51, 53, 55, 61, 63, 65, 80, 81, 82]
            clothing_rec = get_clothing_recommendation(temp_c, condition, is_rainy)
            response_text += f"\n\n👔 **What to Wear:**\n{clothing_rec}"
        
        response_text += "\n\n*🤖 Powered by AI Weather Agent using Open-Meteo API*"
        if not include_clothing:
            response_text += "\n*💡 Ask 'what should I wear?' for clothing recommendations*"
        
        return response_text
        
    except Exception as e:
        return f"❌ Weather service error: {str(e)}"

def get_weather_forecast(city, include_clothing=False):
    """Get 7-day weather forecast with optional clothing advice"""
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(city)}&count=1&language=en&format=json"
        
        with urllib.request.urlopen(geo_url, timeout=10) as response:
            geo_data = json.loads(response.read().decode())
        
        if not geo_data.get('results'):
            if ' ' in city:
                city_only = city.split()[0]
                geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(city_only)}&count=1&language=en&format=json"
                
                with urllib.request.urlopen(geo_url, timeout=10) as response:
                    geo_data = json.loads(response.read().decode())
                
                if not geo_data.get('results'):
                    return f"❌ Could not find forecast for '{city}'. Try just the city name."
            else:
                return f"❌ Could not find forecast for '{city}'. Please check the spelling."
        
        result = geo_data['results'][0]
        lat = result['latitude']
        lon = result['longitude']
        city_name = result['name']
        country = result.get('country', 'Unknown')
        
        # Get 7-day forecast
        forecast_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,weather_code&timezone=auto&forecast_days=7"
        
        with urllib.request.urlopen(forecast_url, timeout=10) as response:
            forecast_data = json.loads(response.read().decode())
        
        daily = forecast_data['daily']
        
        forecast_text = f"📅 **7-Day Weather Forecast for {city_name}, {country}**\n\n"
        
        day_names = ['Today', 'Tomorrow', 'Day 3', 'Day 4', 'Day 5', 'Day 6', 'Day 7']
        
        for i in range(7):
            date = daily['time'][i]
            max_c = round(daily['temperature_2m_max'][i], 1)
            min_c = round(daily['temperature_2m_min'][i], 1)
            max_f = round((max_c * 9/5) + 32, 1)
            min_f = round((min_c * 9/5) + 32, 1)
            code = daily['weather_code'][i]
            
            conditions = {
                0: "Clear", 1: "Clear", 2: "Cloudy", 3: "Overcast",
                45: "Fog", 51: "Drizzle", 61: "Rain", 63: "Rain",
                65: "Heavy rain", 71: "Snow", 80: "Showers", 95: "Thunderstorm"
            }
            condition = conditions.get(code, "Unknown")
            
            day = day_names[i] if i < len(day_names) else f"Day {i+1}"
            
            forecast_text += f"**{day}** ({date}): {max_c}°C/{min_c}°C ({max_f}°F/{min_f}°F) - {condition}\n"
        
        # Add clothing recommendation for tomorrow if requested
        if include_clothing and len(daily['temperature_2m_max']) > 1:
            tomorrow_max = round(daily['temperature_2m_max'][1], 1)
            tomorrow_code = daily['weather_code'][1]
            tomorrow_condition = conditions.get(tomorrow_code, "Unknown")
            
            is_rainy = tomorrow_code in [51, 53, 55, 61, 63, 65, 80, 81, 82]
            clothing_rec = get_clothing_recommendation(tomorrow_max, tomorrow_condition, is_rainy)
            
            forecast_text += f"\n👔 **What to Wear Tomorrow:**\n{clothing_rec}\n"
        
        forecast_text += "\n*🤖 7-day forecast from Open-Meteo API*"
        if not include_clothing:
            forecast_text += "\n*💡 Ask 'what should I wear tomorrow?' for clothing advice*"
        
        return forecast_text
        
    except Exception as e:
        return f"❌ Forecast service error: {str(e)}"

# Keep compatibility
def get_weather_data(city):
    """Compatibility function - defaults to current weather"""
    return get_current_weather(city)
