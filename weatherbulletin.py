#!/usr/bin/python3
"""Weather prompt generator"""
import logging
from collections import defaultdict
from datetime import datetime, timedelta
import json
import sys
import time

import requests
import yaml
from google.cloud import texttospeech
from google.oauth2 import service_account

logging.basicConfig(filename='weather.log', encoding='utf-8', level=logging.DEBUG)

try:
    with open("config.yaml", "r", encoding="utf-8") as f:
        SETTINGS = yaml.safe_load(f)
except FileNotFoundError:
    logging.critical("Error: config.yaml cannot be found. Exiting.")
    sys.exit(1)

# Set up Google TTS client
credentials = service_account.Credentials.from_service_account_file(
    SETTINGS["google_oauth_creds"]
)
tts_client = texttospeech.TextToSpeechClient(credentials=credentials)


class MetOfficeWeatherForecast:
    """Met Office Weather Forecast object"""

    def __init__(self, data):
        self.data = data["features"][0]["properties"]["timeSeries"]

    def _get_daily_data(self):
        daily_data = {}
        for entry in self.data:
            date = entry["time"][:10]
            if date not in daily_data:
                daily_data[date] = []
            daily_data[date].append(entry)
        return daily_data

    def _calculate_high_low(self, temps):
        return max(temps), min(temps)

    def _determine_day_part(self, the_time):
        hour = int(the_time.split("T")[1].split(":")[0])
        if 6 <= hour < 12:
            return "morning"
        if 12 <= hour < 18:
            return "afternoon"
        if 18 <= hour < 24:
            return "evening"
        else:
            return "overnight"

    def _get_day_periods(self, daily_data):
        day_periods = {"morning": [], "afternoon": [], "evening": [], "overnight": []}
        for date, entries in daily_data.items():
            logging.debug(date)
            for entry in entries:
                hour = int(entry["time"][11:13])
                if 7 <= hour < 12:
                    day_periods["morning"].append(entry)
                elif 12 <= hour < 17:
                    day_periods["afternoon"].append(entry)
                elif 17 <= hour < 24:
                    day_periods["evening"].append(entry)
                else:
                    day_periods["overnight"].append(entry)
        return day_periods

    def _get_weather_type(self, weather_code):
        weather_types = {
            0: "Clear night",
            1: "Sunny day",
            2: "Partly cloudy (night)",
            3: "Partly cloudy (day)",
            5: "Mist",
            6: "Fog",
            7: "Cloudy",
            8: "Overcast",
            9: "Light rain shower (night)",
            10: "Light rain shower (day)",
            11: "Drizzle",
            12: "Light rain",
            13: "Heavy rain shower (night)",
            14: "Heavy rain shower (day)",
            15: "Heavy rain",
            16: "Sleet shower (night)",
            17: "Sleet shower (day)",
            18: "Sleet",
            19: "Hail shower (night)",
            20: "Hail shower (day)",
            21: "Hail",
            22: "Light snow shower (night)",
            23: "Light snow shower (day)",
            24: "Light snow",
            25: "Heavy snow shower (night)",
            26: "Heavy snow shower (day)",
            27: "Heavy snow",
            28: "Thunder shower (night)",
            29: "Thunder shower (day)",
            30: "Thunder",
        }
        return weather_types[weather_code]

    def get_weather_forecast_types(self):
        """Get weather forecast types"""
        weather_forecast_types = set()
        for entry in self.data:
            weather_code = entry["significantWeatherCode"]
            weather_type = self._get_weather_type(weather_code)
            if weather_type:
                weather_forecast_types.add(weather_type)
        return list(weather_forecast_types)

    def get_highs_lows(self):
        """Get hour part temp highs/lows"""
        daily_data = self._get_daily_data()
        highs_lows = {}
        for date, entries in daily_data.items():
            logging.debug(entry["maxScreenAirTemp"] for entry in entries)
            temps = [entry["maxScreenAirTemp"] for entry in entries]
            high, low = self._calculate_high_low(temps)
            highs_lows[date] = {"high": round(high), "low": round(low)}
        return highs_lows

    def get_day_periods_weather(self):
        """Get weather periods data"""
        daily_data = self._get_daily_data()
        sorted_dates = sorted(daily_data.keys())

        weather_forecast = defaultdict(dict)

        for date in sorted_dates:
            day_data = daily_data[date]
            day_parts = defaultdict(list)

            for entry in day_data:
                the_time = entry["time"]
                day_part = self._determine_day_part(the_time)
                day_parts[day_part].append(entry)

            for day_part, entries in day_parts.items():
                weather_forecast[date][day_part] = self._get_weather_for_day(entries)

        return weather_forecast

    def _get_weather_for_day(self, entries):
        max_temp = round(max(entry["maxScreenAirTemp"] for entry in entries))
        min_temp = round(min(entry["minScreenAirTemp"] for entry in entries))
        uv_index = max(entry["uvIndex"] for entry in entries)
        prob_of_rain = max(entry["probOfRain"] for entry in entries)
        weather_codes = sorted(
            set(entry["significantWeatherCode"] for entry in entries)
        )

        return {
            "max_temp": max_temp,
            "min_temp": min_temp,
            "weather_code": weather_codes,
            "uv_index": uv_index,
            "prob_of_rain": prob_of_rain,
        }


def bulletin_metoffice() -> str:
    """Return weather bulletin from Met Office"""
    base_url = "https://data.hub.api.metoffice.gov.uk/sitespecific/v0/point/"
    now = datetime.now()
    data = json.loads(
        get_metoffice_forecast(
            base_url,
            "three-hourly",  # hourly or three-hourly
            SETTINGS["lat"],
            SETTINGS["long"],
            False,
            True,
        )
    )
    weather_forecast = MetOfficeWeatherForecast(data)
    forecast = weather_forecast.get_day_periods_weather()
    temps = weather_forecast.get_highs_lows()

    # Sort timing
    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    # Generate the bulletin with the information received
    if now.hour >= 5 and now.hour < 11:
        # Generate morning bulletin
        logging.info("Generating morning bulletin")
        morning_weather = metoffice_weather_codes_to_str(
            forecast[today]["morning"]["weather_code"], "day"
        )
        afternoon_weather = metoffice_weather_codes_to_str(
            forecast[today]["afternoon"]["weather_code"], "day"
        )
        peak_temp = temps[today]
        bulletin = f"{morning_weather} this morning, "
        if morning_weather == afternoon_weather:
            bulletin += "staying much the same throughout the afternoon in North East Somerset, "
        else:
            bulletin += (
                f"{afternoon_weather} across North East Somerset this afternoon "
            )
        bulletin += f"with temperatures reaching {peak_temp} degrees."
    elif now.hour >= 11 and now.hour < 17:
        # Generate afternoon bulletin
        logging.info("Generating afternoon bulletin")
        afternoon_weather = metoffice_weather_codes_to_str(
            forecast[today]["afternoon"]["weather_code"], "day"
        )
        evening_weather = metoffice_weather_codes_to_str(
            forecast[today]["evening"]["weather_code"], "day"
        )
        peak_temp = temps[today]
        bulletin = f"{afternoon_weather} this afternoon"
        if afternoon_weather == evening_weather:
            bulletin += ", continuing into the evening"
        else:
            bulletin += f", {evening_weather} later into the evening"
        bulletin += (
            f". Highs across North East Somerset of {peak_temp['high']} degrees."
        )
    elif now.hour >= 17 and now.hour < 24:
        # Generate evening / tomorrow bulletin
        logging.info("Generating evening bulletin")
        evening_weather = metoffice_weather_codes_to_str(
            forecast[today]["evening"]["weather_code"], "day"
        )
        overnight_weather = metoffice_weather_codes_to_str(
            forecast[tomorrow]["overnight"]["weather_code"], "night"
        )
        tomorrow_weather = metoffice_weather_codes_to_str(
            forecast[tomorrow]["morning"]["weather_code"], "day"
        )
        temps_tomorrow = temps[tomorrow]
        bulletin = f"{evening_weather} this evening. "
        bulletin += (
            f"{overnight_weather} overnight with lows of {temps_tomorrow['low']} degrees. "
        )
        bulletin += f"Tomorrow we will expect {tomorrow_weather} with highs of {temps_tomorrow['high']}."
    else:
        # Generate overnight bulletin
        logging.info("Generating overnight bulletin")
        overnight_weather = metoffice_weather_codes_to_str(
            forecast[tomorrow]["overnight"]["weather_code"], "night"
        )
        tomorrow_morning_weather = metoffice_weather_codes_to_str(
            forecast[tomorrow]["morning"]["weather_code"], "day"
        )
        tomorrow_afternoon_weather = metoffice_weather_codes_to_str(
            forecast[tomorrow]["afternoon"]["weather_code"], "day"
        )
        temps_tomorrow = temps[tomorrow]
        bulletin = (
            f"{overnight_weather} overnight with lows of {temps_tomorrow['low']} degrees. "
        )
        if tomorrow_morning_weather == tomorrow_afternoon_weather:
            bulletin += f"Tomorrow we are expecting {tomorrow_morning_weather}, "
            bulletin += f"with temperatures reaching highs of {temps_tomorrow['high']} degrees."
        else:
            bulletin += f"Tomorrow morning will start with {tomorrow_morning_weather}, "
            bulletin += f"{tomorrow_afternoon_weather} later on, highs of {temps_tomorrow['high']}."

    return bulletin


def metoffice_weather_codes_to_str(codes, part) -> str:
    """Take list of Met Office weather codes and generate a forecast string"""
    values = {
        0: "Clear",
        1: "Clear and sunny",
        2: "Partially cloudy",
        3: "Sunny with a few clouds",
        5: "Misty",
        6: "Foggy",
        7: "Cloudy skies",
        8: "Overcast",
        9: "Light rain showers",
        10: "Light rain showers",
        11: "Drizzle",
        12: "Light rain",
        13: "Heavy rain showers",
        14: "Heavy rain showers",
        15: "Heavy rain",
        16: "Sleet showers",
        17: "Sleet showers",
        18: "Sleet",
        19: "Hail showers",
        20: "Hail showers",
        21: "Hail",
        22: "Light snow showers",
        23: "Light snow showers",
        24: "Light snow",
        25: "Heavy snow showers",
        26: "Heavy snow showers",
        27: "Heavy snow",
        28: "Thunder showers",
        29: "Thunder showers",
        30: "Thunder",
    }
    weather = ""
    i = 0
    day_skip_codes = {1, 2, 3, 4, 5, 6, 7, 8, 11, 12, 15, 18, 21, 24, 27, 30}
    night_skip_codes = {0, 9, 10, 13, 14, 16, 17, 19, 20, 22, 23, 25, 26, 28, 29}

    if part == "night":
        codes_to_skip = day_skip_codes
    elif part == "day":
        codes_to_skip = night_skip_codes

    # Deduplicate similar weather codes
    for code in codes[:]:
        # Remove cloudy skies if sunny with clouds appear.
        if code == 7 and 3 in codes:
            codes.remove(7)
        if code == 2 and 3 in codes:
            codes.remove(2)

    for code in codes:
        if code in codes_to_skip:
            continue
        i = i + 1
        if i == 2 and len(codes) >= 2:
            weather += ", with "
        if i == 3 and len(codes) >= 3:
            weather += " and "
        weather += values.get(code, "Some weather")
    return weather


def get_metoffice_forecast(
    base_url, timesteps, latitude, longitude, exclude_metadata, include_location
) -> str:
    """Generate forecast from Met Office API"""
    url = base_url + timesteps

    headers = {"accept": "application/json", "apikey": SETTINGS["metoffice_api_key"]}
    params = {
        "excludeParameterMetadata": exclude_metadata,
        "includeLocationName": include_location,
        "latitude": latitude,
        "longitude": longitude,
    }

    success = False
    retries = 5

    while not success and retries > 0:
        try:
            req = requests.get(url, headers=headers, params=params, timeout=3)
            success = True
        except requests.RequestException as e:
            logging.warning("Exception occurred: %s", e, exc_info=True)
            retries -= 1
            time.sleep(10)
            if retries == 0:
                logging.error("Retries exceeded. %s", e, exc_info=True)
                sys.exit()

    req.encoding = "utf-8"

    return req.text


def generate_audio(text) -> str:
    """Generate text to speech audio via Google Text-to-Speech API"""
    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
        language_code="en-GB",
        name="en-GB-Neural2-F",
        ssml_gender=texttospeech.SsmlVoiceGender.FEMALE,
    )

    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
        speaking_rate=1.0,
        volume_gain_db=6.0,
        pitch=-4,
    )

    response = tts_client.synthesize_speech(
        input=synthesis_input, voice=voice, audio_config=audio_config
    )
    audio_file = SETTINGS["output_file"]
    with open(audio_file, "wb") as out:
        out.write(response.audio_content)
        print(f"Audio content written to file {audio_file}")
    return audio_file


def main() -> int:
    """Get the weather forecast and generate the bulletin audio"""
    bulletin = bulletin_metoffice()
    logging.info("Bulletin: %s", bulletin)
    audio_file = generate_audio(bulletin)
    logging.info("File updated: %s", audio_file)


if __name__ == "__main__":
    sys.exit(main())
