"""
Journey Service - Internal API for journey operations
Based on legacy authflow JourneyRunner
"""

from pathlib import Path
from typing import Dict, Any, Optional
from loguru import logger

from ...core.journey.journey_models import JourneyConfig, JourneyResult, JourneyError
from ...core.config import ConfigLoader
from ...core.http_client import HTTPClient
from ...core.exceptions import ConfigError


class JourneyService:
    """Journey service for authentication flow execution"""
    
    def __init__(self):
        self.config_loader = ConfigLoader()
        self.http_client = HTTPClient()
        self.logger = logger
    
    async def load_config(self, config_path: Path) -> JourneyConfig:
        """Load and validate journey configuration"""
        try:
            # Load YAML config
            config_data = await self.config_loader.load_yaml(config_path)
            
            # Validate and parse config
            journey_config = JourneyConfig(**config_data)
            
            self.logger.debug(f"Loaded journey config: {journey_config.journey_name}")
            return journey_config
            
        except Exception as e:
            raise ConfigError(f"Failed to load journey config: {e}")
    
    async def run_journey(self, config: JourneyConfig, step_mode: bool = False, timeout: int = 30000) -> JourneyResult:
        """Run authentication journey"""
        try:
            self.logger.info(f"Starting journey: {config.journey_name}")
            
            # Step 1: Initialize journey
            self.logger.info("Initializing authentication journey")
            init_response = await self._init_journey(config, timeout)
            
            if step_mode:
                self.logger.info("Journey initialized!")
                self.logger.info(f"Auth ID: {init_response['authId']}")
                self.logger.info(f"Callbacks received: {len(init_response.get('callbacks', []))}")
                
                # Prompt user to continue
                should_continue = await self._prompt_user("Continue to next step?")
                if not should_continue:
                    return JourneyResult(success=False, error="User cancelled journey")
            
            current_auth_id = init_response['authId']
            current_callbacks = init_response.get('callbacks', [])
            step_number = 2
            
            # Step 2+: Process each step
            step_keys = list(config.steps.keys())
            
            for step_key in step_keys:
                self.logger.info(f"Processing step: {step_key}")
                
                # Process callbacks with step config
                processed_callbacks = self._process_callbacks(current_callbacks, config.steps[step_key])
                
                # Continue journey
                continue_response = await self._continue_journey(
                    current_auth_id, processed_callbacks, config, timeout
                )
                
                # Check if journey is complete
                if continue_response.get('tokenId'):
                    self.logger.info("Authentication successful!")
                    return JourneyResult(
                        success=True,
                        token_id=continue_response['tokenId'],
                        success_url=continue_response.get('successUrl')
                    )
                
                if step_mode:
                    self.logger.info(f"Step {step_number - 1} completed!")
                    self.logger.info(f"New Auth ID: {continue_response['authId']}")
                    self.logger.info(f"Callbacks received: {len(continue_response.get('callbacks', []))}")
                    
                    should_continue = await self._prompt_user("Continue to next step?")
                    if not should_continue:
                        return JourneyResult(success=False, error="User cancelled journey")
                
                # Continue with next step
                current_auth_id = continue_response['authId']
                current_callbacks = continue_response.get('callbacks', [])
                step_number += 1
            
            raise JourneyError("Journey completed but no token received")
            
        except Exception as e:
            self.logger.error(f"Journey failed: {e}")
            return JourneyResult(success=False, error=str(e))
    
    async def _init_journey(self, config: JourneyConfig, timeout: int) -> Dict[str, Any]:
        """Initialize authentication journey"""
        url = f"{config.platform_url}/am/json/realms/root/realms/{config.realm}/authenticate"
        params = {"authIndexType": "service", "authIndexValue": config.journey_name}
        
        # ForgeRock AM required headers
        headers = {
            "Content-Type": "application/json",
            "Accept-API-Version": "resource=2.0, protocol=1.0"
        }
        
        response = await self.http_client.post(url, params=params, headers=headers, timeout=timeout/1000)
        return response
    
    async def _continue_journey(self, auth_id: str, callbacks: list, config: JourneyConfig, timeout: int) -> Dict[str, Any]:
        """Continue authentication journey"""
        url = f"{config.platform_url}/am/json/realms/root/realms/{config.realm}/authenticate"
        
        payload = {
            "authId": auth_id,
            "callbacks": callbacks
        }
        
        # ForgeRock AM required headers
        headers = {
            "Content-Type": "application/json",
            "Accept-API-Version": "resource=2.0, protocol=1.0"
        }
        
        response = await self.http_client.post(url, json=payload, headers=headers, timeout=timeout/1000)
        return response
    
    def _process_callbacks(self, callbacks: list, step_config: Dict[str, str]) -> list:
        """Process callbacks with intelligent prompt matching - from working TypeScript implementation"""
        self.logger.debug('Processing callbacks with intelligent prompt matching')
        
        processed_callbacks = []
        
        for callback in callbacks:
            processed_callback = callback.copy()
            processed_inputs = []
            
            for input_field in callback.get('input', []):
                # First try intelligent prompt matching
                config_value = self._match_by_prompt(callback, input_field.get('name'), step_config)
                
                # Fallback to direct field name matching for backward compatibility
                fallback_value = step_config.get(input_field.get('name'))
                
                processed_input = input_field.copy()
                processed_input['value'] = config_value or fallback_value or input_field.get('value', '')
                processed_inputs.append(processed_input)
            
            processed_callback['input'] = processed_inputs
            processed_callbacks.append(processed_callback)
        
        return processed_callbacks
    
    def _match_by_prompt(self, callback: Dict, input_name: str, step_config: Dict[str, str]) -> Optional[str]:
        """Extract prompt text from callback output and match with config"""
        # Extract prompt text from callback output
        prompt_output = None
        for output in callback.get('output', []):
            if output.get('name') == 'prompt':
                prompt_output = output
                break
        
        if not prompt_output:
            self.logger.debug(f"No prompt found for callback type: {callback.get('type')}")
            return None
        
        prompt_text = prompt_output.get('value', '')
        self.logger.debug(f"Looking for prompt: \"{prompt_text}\" (field: {input_name})")
        
        # Try exact match first
        if prompt_text in step_config:
            self.logger.debug(f"Exact prompt match found: \"{prompt_text}\" -> \"{step_config[prompt_text]}\"")
            return step_config[prompt_text]
        
        # Try case-insensitive match
        lower_prompt = prompt_text.lower()
        for config_key, config_value in step_config.items():
            if config_key.lower() == lower_prompt:
                self.logger.debug(f"Case-insensitive prompt match: \"{config_key}\" -> \"{config_value}\"")
                return config_value
        
        # Try fuzzy matching for common patterns
        fuzzy_match = self._fuzzy_match_prompt(prompt_text, step_config)
        if fuzzy_match:
            self.logger.debug(f"Fuzzy prompt match: \"{prompt_text}\" -> \"{fuzzy_match['key']}\" -> \"{fuzzy_match['value']}\"")
            return fuzzy_match['value']
        
        self.logger.debug(f"No prompt match found for: \"{prompt_text}\"")
        return None
    
    def _fuzzy_match_prompt(self, prompt_text: str, step_config: Dict[str, str]) -> Optional[Dict[str, str]]:
        """Fuzzy matching for common prompt patterns"""
        lower_prompt = prompt_text.lower()
        
        # Common prompt patterns and their variations
        patterns = [
            {'patterns': ['username', 'user name', 'user', 'email', 'login'], 'prompt': lower_prompt},
            {'patterns': ['password', 'pass', 'pwd'], 'prompt': lower_prompt},
            {'patterns': ['code', 'otp', 'token', 'verification', 'verify'], 'prompt': lower_prompt},
            {'patterns': ['phone', 'mobile', 'sms'], 'prompt': lower_prompt}
        ]
        
        for config_key, config_value in step_config.items():
            lower_config_key = config_key.lower()
            
            # Check if any pattern matches both prompt and config key
            for pattern in patterns:
                prompt_matches = any(p in pattern['prompt'] for p in pattern['patterns'])
                config_matches = any(p in lower_config_key for p in pattern['patterns'])
                
                if prompt_matches and config_matches:
                    return {'key': config_key, 'value': config_value}
            
            # Check for partial matches (contains)
            if lower_prompt in lower_config_key or lower_config_key in lower_prompt:
                return {'key': config_key, 'value': config_value}
        
        return None
    
    async def _prompt_user(self, message: str) -> bool:
        """Prompt user for confirmation in step mode"""
        try:
            # Simple implementation for step mode
            response = input(f"{message} (y/N): ").lower().strip()
            return response in ['y', 'yes']
        except (EOFError, KeyboardInterrupt):
            return False