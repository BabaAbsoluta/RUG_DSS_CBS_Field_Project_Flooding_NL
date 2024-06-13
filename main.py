import pandas as pd
import geopandas as gpd
import folium
import branca.colormap as cm
import requests
import cbsodata
from functools import lru_cache

# Load the required files
historical_flooding_data = gpd.read_file('flooding_data/ror_historische_overstromingen.gpkg')
city_data = pd.read_csv('City_data/nl.csv')
for col in historical_flooding_data.columns:
    if pd.api.types.is_datetime64_any_dtype(historical_flooding_data[col]):
        historical_flooding_data[col] = historical_flooding_data[col].dt.strftime('%Y-%m-%d')
# Ensure the data is in WGS84
historical_flooding_data = historical_flooding_data.to_crs(epsg=4326)


# Function to fetch features with pagination
@lru_cache(maxsize=None)
def fetch_features(url):
    all_features = []
    start_index = 0
    page_size = 1000  # Adjust as needed

    while True:
        params = {
            "service": "wfs",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeName": url.split("typeName=")[-1].split("&")[0],
            "outputFormat": "json",
            "startIndex": start_index,
            "count": page_size
        }
        response = requests.get(url, params=params)
        data = response.json()
        features = data.get("features", [])
        all_features.extend(features)
        if len(features) < page_size:
            break
        start_index += page_size

    return all_features


# URL to fetch municipal boundaries
geodata_url_gemeente = 'https://service.pdok.nl/cbs/gebiedsindelingen/2023/wfs/v1_0?request=GetFeature&typeName=gemeente_gegeneraliseerd'

# Fetch features for municipalities
gemeente_features = fetch_features(geodata_url_gemeente)

# Convert features to GeoPandas DataFrame
gemeentegrenzen = gpd.GeoDataFrame.from_features(gemeente_features)

# Make sure your data is in the correct CRS
gemeentegrenzen = gemeentegrenzen.set_crs(epsg=28992, allow_override=True)
gemeentegrenzen = gemeentegrenzen.to_crs(epsg=4326)  # Convert to WGS84

# Fetch CBS data
cbs_data = pd.DataFrame(cbsodata.get_data('83765NED', select=[
    'WijkenEnBuurten', 'Codering_3', 'GemiddeldInkomenPerInwoner_66',
    'ScholenBinnen3Km_98', 'ALandbouwBosbouwEnVisserij_79', 'BFNijverheidEnEnergie_80',
    'k_65JaarOfOuder_12', 'k_0Tot15Jaar_8', 'Bevolkingsdichtheid_33', 'HuishOnderOfRondSociaalMinimum_73'
]))

# Clean CBS data
cbs_data['Codering_3'] = cbs_data['Codering_3'].str.strip()

# Merge CBS data with municipal boundaries GeoDataFrame
combined_data = gemeentegrenzen.merge(cbs_data, left_on='statcode', right_on='Codering_3', how='left')

# Ensure the new columns are numeric and preserve NaNs
columns_to_convert = [
    'GemiddeldInkomenPerInwoner_66', 'ScholenBinnen3Km_98', 'ALandbouwBosbouwEnVisserij_79',
    'BFNijverheidEnEnergie_80', 'k_65JaarOfOuder_12', 'k_0Tot15Jaar_8', 'Bevolkingsdichtheid_33',
    'HuishOnderOfRondSociaalMinimum_73'
]
for col in columns_to_convert:
    combined_data[col] = pd.to_numeric(combined_data[col], errors='coerce')

# Initialize the map
m = folium.Map(location=[52.1326, 5.2913], zoom_start=7)

# Define color scales for the data
color_scales = {
    'GemiddeldInkomenPerInwoner_66': cm.LinearColormap(
        colors=['blue', 'cyan', 'green', 'yellow', 'orange', 'red'],
        vmin=combined_data['GemiddeldInkomenPerInwoner_66'].min(),
        vmax=combined_data['GemiddeldInkomenPerInwoner_66'].max(),
        caption='Average Income per Resident (x1000 €)'
    ),
    'ScholenBinnen3Km_98': cm.LinearColormap(
        colors=['white', 'darkblue'],
        vmin=combined_data['ScholenBinnen3Km_98'].min(),
        vmax=combined_data['ScholenBinnen3Km_98'].max(),
        caption='Schools within 3 km'
    ),
    'ALandbouwBosbouwEnVisserij_79': cm.LinearColormap(
        colors=['white', 'green'],
        vmin=combined_data['ALandbouwBosbouwEnVisserij_79'].min(),
        vmax=combined_data['ALandbouwBosbouwEnVisserij_79'].max(),
        caption='Agriculture, Forestry, and Fishing'
    ),
    'BFNijverheidEnEnergie_80': cm.LinearColormap(
        colors=['white', 'orange'],
        vmin=combined_data['BFNijverheidEnEnergie_80'].min(),
        vmax=combined_data['BFNijverheidEnEnergie_80'].max(),
        caption='Industry and Energy'
    ),
    'k_65JaarOfOuder_12': cm.LinearColormap(
        colors=['white', 'purple'],
        vmin=combined_data['k_65JaarOfOuder_12'].min(),
        vmax=combined_data['k_65JaarOfOuder_12'].max(),
        caption='65 years or older'
    ),
    'k_0Tot15Jaar_8': cm.LinearColormap(
        colors=['white', 'pink'],
        vmin=combined_data['k_0Tot15Jaar_8'].min(),
        vmax=combined_data['k_0Tot15Jaar_8'].max(),
        caption='0 to 15 years'
    ),
    'Bevolkingsdichtheid_33': cm.LinearColormap(
        colors=['white', 'brown'],
        vmin=combined_data['Bevolkingsdichtheid_33'].min(),
        vmax=combined_data['Bevolkingsdichtheid_33'].max(),
        caption='Population Density'
    ),
    'HuishOnderOfRondSociaalMinimum_73': cm.LinearColormap(
        colors=['white', 'red'],
        vmin=combined_data['HuishOnderOfRondSociaalMinimum_73'].min(),
        vmax=combined_data['HuishOnderOfRondSociaalMinimum_73'].max(),
        caption='Households under or around social minimum'
    ),
}


def add_geojson_layer(data, column, color_scale, name, aliases):
    folium.GeoJson(
        data.to_json(),
        name=name,
        style_function=lambda feature: {
            'fillColor': color_scale(feature['properties'][column]) if pd.notnull(
                feature['properties'][column]) else '#D3D3D3',
            'color': 'black',
            'weight': 1,
            'fillOpacity': 0.7
        },
        tooltip=folium.GeoJsonTooltip(
            fields=['statnaam', column],
            aliases=aliases,
            localize=True
        )
    ).add_to(m)


# Add all layers to the map
add_geojson_layer(combined_data, 'GemiddeldInkomenPerInwoner_66', color_scales['GemiddeldInkomenPerInwoner_66'],
                  'Average Income per Resident', ['Municipality:', 'Average Income (x1000 €):'])
add_geojson_layer(combined_data, 'ScholenBinnen3Km_98', color_scales['ScholenBinnen3Km_98'], 'Schools within 3 km',
                  ['Municipality:', 'Schools within 3 km:'])
add_geojson_layer(combined_data, 'ALandbouwBosbouwEnVisserij_79', color_scales['ALandbouwBosbouwEnVisserij_79'],
                  'Agriculture, Forestry, and Fishing', ['Municipality:', 'Agriculture, Forestry, and Fishing:'])
add_geojson_layer(combined_data, 'BFNijverheidEnEnergie_80', color_scales['BFNijverheidEnEnergie_80'],
                  'Industry and Energy', ['Municipality:', 'Industry and Energy:'])
add_geojson_layer(combined_data, 'k_65JaarOfOuder_12', color_scales['k_65JaarOfOuder_12'], '65 years or older',
                  ['Municipality:', '65 years or older:'])
add_geojson_layer(combined_data, 'k_0Tot15Jaar_8', color_scales['k_0Tot15Jaar_8'], '0 to 15 years',
                  ['Municipality:', '0 to 15 years:'])
add_geojson_layer(combined_data, 'Bevolkingsdichtheid_33', color_scales['Bevolkingsdichtheid_33'], 'Population Density',
                  ['Municipality:', 'Population Density:'])
add_geojson_layer(combined_data, 'HuishOnderOfRondSociaalMinimum_73', color_scales['HuishOnderOfRondSociaalMinimum_73'],
                  'Households under or around social minimum',
                  ['Municipality:', 'Households under or around social minimum:'])

folium.GeoJson(
    historical_flooding_data,
    name="Historical Flooding",
    style_function=lambda feature: {
        'fillColor': 'blue',
        'color': 'black',
        'weight': 1,
        'fillOpacity': 0.3
    }
).add_to(m)
city_layer = folium.FeatureGroup(name="Cities")

# Add city markers
for idx, row in city_data.iterrows():
    folium.CircleMarker(
        [row['lat'], row['lng']],
        radius=5,  # Set the radius for the circle
        popup=f"{row['city']}, Population: {row['population']}",
        color='green',  # Outline color
        fill=True,
        fill_color='red',  # Fill color
        fill_opacity=0.7  # Fill opacity
    ).add_to(city_layer)

city_layer.add_to(m)

# Add the color scales to the map
for scale in color_scales.values():
    scale.add_to(m)

# Add the color scales to the map
for scale in color_scales.values():
    scale.add_to(m)

# Add layer control to switch between layers
folium.LayerControl().add_to(m)

# Save the map
m.save("map-with-all-layers.html-final-version.html")