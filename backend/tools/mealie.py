"""Mealie recipe management integration"""
import json
from typing import Dict, Any, Optional

try:
    from backend.tools import terminal, web, config
except ImportError:
    try:
        from tools import terminal, web, config
    except ImportError:
        from . import terminal, web, config


def _success(output):
    return {"status": "success", "output": output}


def _error(message):
    return {"status": "error", "error": message}


def _get_mealie_config() -> tuple:
    """Get Mealie API configuration"""
    # Get Mealie URL
    url_result = config.get_config("mealie.url")
    if url_result.get("status") != "success":
        return None, None, "Mealie URL not configured. Use: config.set('mealie.url', 'https://your-mealie-url')"
    
    # Get API token
    token_result = config.get_config("mealie.api_token")
    if token_result.get("status") != "success":
        return None, None, "Mealie API token not configured. Use: config.set('mealie.api_token', 'your-token')"
    
    url = url_result.get("output", {}).get("value", "").rstrip('/')
    token = token_result.get("output", {}).get("value", "")
    
    return url, token, None


def search_recipe_online(query: str, language: str = "de") -> Dict[str, Any]:
    """
    Search for recipes online (German cooking sites prioritized).
    
    Args:
        query: Recipe search query (e.g., "Käsekuchen", "Gulasch")
        language: Language code (default: "de" for German)
    
    Returns:
        Dict with search results and recipe URLs
    """
    try:
        if not query or not query.strip():
            return _error("Search query cannot be empty")
        
        # For German recipes, search Chefkoch.de
        if language == "de" or language.startswith("de"):
            search_url = f"https://www.chefkoch.de/rs/s0/{query.replace(' ', '+')}/Rezepte.html"
            
            # Fetch search results
            fetch_result = web.fetch_url(search_url, timeout=20)
            if fetch_result.get("status") != "success":
                return _error(f"Failed to search recipes: {fetch_result.get('error')}")
            
            content = fetch_result.get("output", {}).get("content", "")
            
            # Extract recipe links
            import re
            recipe_links = re.findall(r'href="(/rezepte/[^"]+)"', content)
            
            # Remove duplicates and limit to top 5
            unique_links = []
            seen = set()
            for link in recipe_links:
                if link not in seen and not link.endswith('#'):
                    seen.add(link)
                    unique_links.append(f"https://www.chefkoch.de{link}")
                    if len(unique_links) >= 5:
                        break
            
            if not unique_links:
                return _error("No recipes found for this search query")
            
            return _success({
                "query": query,
                "language": language,
                "count": len(unique_links),
                "recipes": unique_links,
                "source": "Chefkoch.de"
            })
        
        else:
            # For English, could add AllRecipes.com or other sites
            return _error(f"Language '{language}' not yet supported. Currently supported: 'de' (German)")
        
    except Exception as e:
        return _error(f"Recipe search failed: {str(e)}")


def add_recipe_from_url(url: str, tags: Optional[list] = None) -> Dict[str, Any]:
    """
    Extract recipe from URL and add it to Mealie.
    
    Args:
        url: Recipe URL to extract and add
        tags: Optional list of tags to add to the recipe
    
    Returns:
        Dict with recipe addition status
    """
    try:
        # Get Mealie configuration
        mealie_url, api_token, error = _get_mealie_config()
        if error:
            return _error(error)
        
        # Extract recipe from URL
        extract_result = web.extract_recipe(url)
        if extract_result.get("status") != "success":
            return extract_result
        
        recipe_data = extract_result.get("output", {})
        
        # Prepare Mealie API payload
        mealie_recipe = {
            "name": recipe_data.get("title", "Untitled Recipe"),
            "description": f"Imported from {url}",
            "recipeIngredient": recipe_data.get("ingredients", []),
            "recipeInstructions": [
                {"text": step} for step in recipe_data.get("instructions", [])
            ],
            "recipeYield": str(recipe_data.get("servings", "")) if recipe_data.get("servings") else None,
            "prepTime": recipe_data.get("prep_time"),
            "performTime": recipe_data.get("cook_time"),
            "tags": tags or [],
            "orgURL": url
        }
        
        # Remove None values
        mealie_recipe = {k: v for k, v in mealie_recipe.items() if v is not None}
        
        # Convert to JSON
        recipe_json = json.dumps(mealie_recipe)
        recipe_json_escaped = recipe_json.replace('"', '\\"').replace("'", "\\'")
        
        # Add recipe to Mealie via API
        curl_cmd = f'''curl -s -X POST "{mealie_url}/api/recipes/create-url" \
            -H "Authorization: Bearer {api_token}" \
            -H "Content-Type: application/json" \
            -d '{recipe_json}' '''
        
        result = terminal.run(curl_cmd, timeout_seconds=30)
        
        if result.get("status") != "success":
            return _error(f"Failed to add recipe to Mealie: {result.get('error')}")
        
        # Parse response
        response_text = result.get("output", "")
        try:
            response_data = json.loads(response_text) if response_text else {}
        except:
            response_data = {}
        
        # Check if successful
        if "slug" in response_data or "id" in response_data:
            recipe_id = response_data.get("slug") or response_data.get("id")
            return _success({
                "added": True,
                "recipe_name": recipe_data.get("title"),
                "recipe_id": recipe_id,
                "mealie_url": f"{mealie_url}/recipe/{recipe_id}",
                "ingredients_count": len(recipe_data.get("ingredients", [])),
                "steps_count": len(recipe_data.get("instructions", []))
            })
        else:
            # Try alternative: Import via URL endpoint
            url_import_cmd = f'''curl -s -X POST "{mealie_url}/api/recipes/create-url" \
                -H "Authorization: Bearer {api_token}" \
                -H "Content-Type: application/json" \
                -d '{{"url": "{url}"}}'  '''
            
            url_result = terminal.run(url_import_cmd, timeout_seconds=30)
            
            if url_result.get("status") == "success":
                try:
                    url_response = json.loads(url_result.get("output", "{}"))
                    if "slug" in url_response:
                        return _success({
                            "added": True,
                            "recipe_name": url_response.get("name", recipe_data.get("title")),
                            "recipe_id": url_response.get("slug"),
                            "mealie_url": f"{mealie_url}/recipe/{url_response.get('slug')}",
                            "method": "url_import"
                        })
                except:
                    pass
            
            return _error(f"Mealie API returned unexpected response. Recipe may not have been added. Response: {response_text[:200]}")
        
    except Exception as e:
        return _error(f"Failed to add recipe: {str(e)}")


def list_recipes(tags: Optional[list] = None, search: Optional[str] = None) -> Dict[str, Any]:
    """
    List recipes from Mealie.
    
    Args:
        tags: Optional list of tags to filter by
        search: Optional search query
    
    Returns:
        Dict with recipe list
    """
    try:
        # Get Mealie configuration
        mealie_url, api_token, error = _get_mealie_config()
        if error:
            return _error(error)
        
        # Build API URL
        api_url = f"{mealie_url}/api/recipes"
        
        # Add query parameters
        params = []
        if search:
            params.append(f"search={search}")
        if tags:
            for tag in tags:
                params.append(f"tags={tag}")
        
        if params:
            api_url += "?" + "&".join(params)
        
        # Fetch recipes
        curl_cmd = f'curl -s -X GET "{api_url}" -H "Authorization: Bearer {api_token}"'
        result = terminal.run(curl_cmd, timeout_seconds=20)
        
        if result.get("status") != "success":
            return _error(f"Failed to list recipes: {result.get('error')}")
        
        # Parse response
        response_text = result.get("output", "")
        try:
            recipes = json.loads(response_text)
        except:
            return _error("Failed to parse Mealie API response")
        
        # Extract basic info
        recipe_list = []
        if isinstance(recipes, dict) and "items" in recipes:
            items = recipes.get("items", [])
        elif isinstance(recipes, list):
            items = recipes
        else:
            items = []
        
        for recipe in items[:20]:  # Limit to 20
            recipe_list.append({
                "name": recipe.get("name"),
                "slug": recipe.get("slug"),
                "description": recipe.get("description", "")[:100],
                "tags": recipe.get("tags", [])
            })
        
        return _success({
            "count": len(recipe_list),
            "recipes": recipe_list
        })
        
    except Exception as e:
        return _error(f"Failed to list recipes: {str(e)}")


def translate_recipe(text: str, source_lang: str = "de", target_lang: str = "en") -> Dict[str, Any]:
    """
    Translate recipe text (basic translation - German/English).
    
    Args:
        text: Text to translate
        source_lang: Source language code (de or en)
        target_lang: Target language code (de or en)
    
    Returns:
        Dict with translated text
    """
    try:
        if not text or not text.strip():
            return _error("Text to translate cannot be empty")
        
        # Basic word-by-word translation for common cooking terms
        # In production, this would use a translation API
        
        translations_de_to_en = {
            # Measurements
            "gramm": "grams", "g": "g",
            "kilogramm": "kilograms", "kg": "kg",
            "liter": "liter", "l": "l",
            "milliliter": "milliliters", "ml": "ml",
            "teelöffel": "teaspoon", "tl": "tsp",
            "esslöffel": "tablespoon", "el": "tbsp",
            "prise": "pinch",
            "tasse": "cup",
            
            # Common ingredients
            "mehl": "flour",
            "zucker": "sugar",
            "salz": "salt",
            "pfeffer": "pepper",
            "butter": "butter",
            "milch": "milk",
            "eier": "eggs",
            "ei": "egg",
            "wasser": "water",
            "öl": "oil",
            "zwiebel": "onion",
            "zwiebeln": "onions",
            "knoblauch": "garlic",
            "kartoffeln": "potatoes",
            "kartoffel": "potato",
            "tomate": "tomato",
            "tomaten": "tomatoes",
            
            # Verbs
            "schneiden": "cut",
            "hacken": "chop",
            "kochen": "cook/boil",
            "braten": "fry",
            "backen": "bake",
            "mischen": "mix",
            "rühren": "stir",
            "erhitzen": "heat",
        }
        
        if source_lang == "de" and target_lang == "en":
            translated = text
            for de, en in translations_de_to_en.items():
                translated = translated.replace(de, en)
                translated = translated.replace(de.capitalize(), en.capitalize())
        elif source_lang == "en" and target_lang == "de":
            # Reverse dictionary
            translations_en_to_de = {v: k for k, v in translations_de_to_en.items()}
            translated = text
            for en, de in translations_en_to_de.items():
                translated = translated.replace(en, de)
                translated = translated.replace(en.capitalize(), de.capitalize())
        else:
            return _error(f"Translation from {source_lang} to {target_lang} not supported")
        
        return _success({
            "original": text,
            "translated": translated,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "note": "Basic word translation - for full sentences, consider using a translation API"
        })
        
    except Exception as e:
        return _error(f"Translation failed: {str(e)}")
