"""Web scraping and content extraction tools"""
import re
import json
from typing import Dict, Any, Optional
from urllib.parse import urlparse

try:
    from backend.tools import terminal
except ImportError:
    try:
        from tools import terminal
    except ImportError:
        from . import terminal


def _success(output):
    return {"status": "success", "output": output}


def _error(message):
    return {"status": "error", "error": message}


def fetch_url(url: str, timeout: int = 30) -> Dict[str, Any]:
    """
    Fetch content from a URL using curl.
    
    Args:
        url: URL to fetch
        timeout: Request timeout in seconds (default: 30)
    
    Returns:
        Dict with page content and metadata
    """
    try:
        if not url or not url.strip():
            return _error("URL cannot be empty")
        
        # Validate URL format
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return _error("Invalid URL format. Must include http:// or https://")
        
        # Use curl to fetch content
        cmd = f'curl -L -s --max-time {timeout} -H "User-Agent: Mozilla/5.0" "{url}"'
        result = terminal.run(cmd, timeout_seconds=timeout + 5)
        
        if result.get("status") != "success":
            return _error(f"Failed to fetch URL: {result.get('error', 'Unknown error')}")
        
        content = result.get("output", "")
        
        if not content:
            return _error("No content received from URL")
        
        return _success({
            "url": url,
            "content": content,
            "size_bytes": len(content),
            "content_preview": content[:500]
        })
        
    except Exception as e:
        return _error(f"Failed to fetch URL: {str(e)}")


def extract_recipe(url: str) -> Dict[str, Any]:
    """
    Extract recipe information from a URL (German cooking sites supported).
    
    Args:
        url: Recipe URL (supports Chefkoch.de and other common formats)
    
    Returns:
        Dict with structured recipe data
    """
    try:
        # Fetch the page
        fetch_result = fetch_url(url)
        if fetch_result.get("status") != "success":
            return fetch_result
        
        content = fetch_result.get("output", {}).get("content", "")
        
        # Initialize recipe data
        recipe = {
            "url": url,
            "title": None,
            "ingredients": [],
            "instructions": [],
            "servings": None,
            "prep_time": None,
            "cook_time": None,
            "difficulty": None,
            "tags": []
        }
        
        # Try to extract title
        title_patterns = [
            r'<title>([^<]+)</title>',
            r'<h1[^>]*>([^<]+)</h1>',
            r'"name":\s*"([^"]+)"',
        ]
        
        for pattern in title_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                recipe["title"] = match.group(1).strip()
                # Clean up common title suffixes
                recipe["title"] = re.sub(r'\s*[-|]\s*(Rezept|Recipe|Chefkoch).*$', '', recipe["title"], flags=re.IGNORECASE)
                break
        
        # Extract servings
        servings_patterns = [
            r'(\d+)\s*(Portionen|servings|Personen)',
            r'"recipeYield":\s*"?(\d+)',
        ]
        
        for pattern in servings_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                recipe["servings"] = int(match.group(1))
                break
        
        # Extract prep/cook time
        time_patterns = [
            r'(Arbeitszeit|Prep\s*time):\s*(?:ca\.\s*)?(\d+)\s*(Min|Std|min|hours?)',
            r'"prepTime":\s*"PT(\d+)M',
            r'(Koch-?zeit|Cook\s*time):\s*(?:ca\.\s*)?(\d+)\s*(Min|Std|min|hours?)',
            r'"cookTime":\s*"PT(\d+)M',
        ]
        
        for pattern in time_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                if 'prep' in pattern.lower() or 'arbeitszeit' in pattern.lower():
                    recipe["prep_time"] = f"{match.group(2)} {match.group(3)}" if len(match.groups()) >= 3 else f"{match.group(1)} min"
                else:
                    recipe["cook_time"] = f"{match.group(2)} {match.group(3)}" if len(match.groups()) >= 3 else f"{match.group(1)} min"
        
        # Extract difficulty
        difficulty_match = re.search(r'(Schwierigkeitsgrad|difficulty):\s*(\w+)', content, re.IGNORECASE)
        if difficulty_match:
            recipe["difficulty"] = difficulty_match.group(2)
        
        # Try to extract structured ingredients (JSON-LD format common on recipe sites)
        json_ld_match = re.search(r'<script[^>]*type="application/ld\+json"[^>]*>(.+?)</script>', content, re.DOTALL)
        if json_ld_match:
            try:
                json_data = json.loads(json_ld_match.group(1))
                if isinstance(json_data, dict):
                    if 'recipeIngredient' in json_data:
                        recipe["ingredients"] = json_data['recipeIngredient']
                    if 'recipeInstructions' in json_data:
                        instructions = json_data['recipeInstructions']
                        if isinstance(instructions, list):
                            recipe["instructions"] = [
                                instr.get('text', str(instr)) if isinstance(instr, dict) else str(instr)
                                for instr in instructions
                            ]
            except:
                pass
        
        # Fallback: Extract from HTML lists if JSON-LD didn't work
        if not recipe["ingredients"]:
            # Look for ingredient lists
            ingredient_section = re.search(r'<(?:div|section)[^>]*(?:ingredient|zutat)[^>]*>(.*?)</(?:div|section)>', content, re.DOTALL | re.IGNORECASE)
            if ingredient_section:
                ingredients_html = ingredient_section.group(1)
                # Find list items
                li_items = re.findall(r'<li[^>]*>([^<]+)</li>', ingredients_html)
                recipe["ingredients"] = [item.strip() for item in li_items if item.strip()]
        
        if not recipe["instructions"]:
            # Look for instruction lists
            instruction_section = re.search(r'<(?:div|section)[^>]*(?:instruction|zubereitung|preparation)[^>]*>(.*?)</(?:div|section)>', content, re.DOTALL | re.IGNORECASE)
            if instruction_section:
                instructions_html = instruction_section.group(1)
                # Find ordered list items or paragraphs
                steps = re.findall(r'<(?:li|p)[^>]*>([^<]+)</(?:li|p)>', instructions_html)
                recipe["instructions"] = [step.strip() for step in steps if step.strip() and len(step.strip()) > 20]
        
        # Clean HTML entities and tags from extracted data
        def clean_text(text):
            if not text:
                return text
            # Remove HTML tags
            text = re.sub(r'<[^>]+>', '', text)
            # Decode common entities
            text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&quot;', '"')
            text = text.replace('&lt;', '<').replace('&gt;', '>')
            return text.strip()
        
        recipe["title"] = clean_text(recipe["title"])
        recipe["ingredients"] = [clean_text(ing) for ing in recipe["ingredients"]]
        recipe["instructions"] = [clean_text(inst) for inst in recipe["instructions"]]
        
        # Validate we got something useful
        if not recipe["title"]:
            return _error("Could not extract recipe title from page")
        
        if not recipe["ingredients"] and not recipe["instructions"]:
            return _error("Could not extract recipe ingredients or instructions. This site may not be supported.")
        
        return _success(recipe)
        
    except Exception as e:
        return _error(f"Failed to extract recipe: {str(e)}")


def extract_text(url: str, selector: Optional[str] = None) -> Dict[str, Any]:
    """
    Extract clean text content from a URL.
    
    Args:
        url: URL to extract text from
        selector: Optional CSS selector or search term to focus extraction
    
    Returns:
        Dict with extracted text
    """
    try:
        # Fetch the page
        fetch_result = fetch_url(url)
        if fetch_result.get("status") != "success":
            return fetch_result
        
        content = fetch_result.get("output", {}).get("content", "")
        
        # Remove scripts and styles
        content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
        
        # If selector provided, try to extract that section
        if selector:
            # Simple ID or class selector support
            if selector.startswith('#'):
                # ID selector
                pattern = f'<[^>]*id=["\']?{selector[1:]}["\']?[^>]*>(.*?)</[^>]+>'
            elif selector.startswith('.'):
                # Class selector
                pattern = f'<[^>]*class=["\'][^"\']*{selector[1:]}[^"\']*["\'][^>]*>(.*?)</[^>]+>'
            else:
                # Search for text containing selector
                pattern = f'<(?:div|section|article)[^>]*>(.*?{re.escape(selector)}.*?)</(?:div|section|article)>'
            
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
            if match:
                content = match.group(1)
        
        # Remove all HTML tags
        text = re.sub(r'<[^>]+>', ' ', content)
        
        # Decode HTML entities
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&quot;', '"')
        text = text.replace('&lt;', '<').replace('&gt;', '>').replace('&apos;', "'")
        
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        
        if not text:
            return _error("No text content extracted from page")
        
        return _success({
            "url": url,
            "text": text,
            "length": len(text),
            "preview": text[:500]
        })
        
    except Exception as e:
        return _error(f"Failed to extract text: {str(e)}")
