import logging
import random
from collections import defaultdict
from typing import List, Dict, Optional, Any

from ..services.openrouter_service import openrouter_service

logger = logging.getLogger(__name__)


async def analyze_tone_for_language(language_emails: List[Dict], user_email: str, language: str) -> Optional[str]:
    """
    Analyzes the user's tone of voice for a single language and returns only the profile string.
    """
    if len(language_emails) < 10:
        logger.info(f"Skipping tone analysis for language '{language}' due to insufficient emails ({len(language_emails)} < 10).")
        return None

    # Group emails by thread
    threads = defaultdict(list)
    for email in language_emails:
        threads[email['thread_id']].append(email)

    # Filter for messages where the user replies to someone else, creating context/response segments.
    candidate_segments = []
    for thread_id, messages in threads.items():
        # A thread is a list of messages sorted chronologically.
        for i, message in enumerate(messages):
            # We are looking for a message from the user.
            sender = message.get('sender', '')
            if user_email in sender:
                # This is a user message. Check if it's a reply to someone else.
                if i > 0:
                    prev_message = messages[i - 1]
                    prev_sender = prev_message.get('sender', '')
                    if user_email not in prev_sender:
                        # This is an "Other -> User" transition.
                        # The context is the single message just before the user's reply.
                        context_messages = [prev_message]
                        user_response_message = message
                        candidate_segments.append({
                            "context": context_messages,
                            "response": user_response_message
                        })

    if not candidate_segments:
            logger.info(f"No suitable candidate segments found for language '{language}' for tone analysis.")
            return None

    # Select 10 random segments, or fewer if not enough are available.
    num_to_select = min(10, len(candidate_segments))
    selected_segments = random.sample(candidate_segments, num_to_select)
    
    logger.info(f"Selected {len(selected_segments)} segments for language '{language}' to analyze tone.")

    few_shot_examples = []
    for segment in selected_segments:
        thread_context = segment['context']
        user_response = segment['response'] # The "good" example

        # Format context for the prompt
        context_str = f"From: {thread_context[0]['sender']}\n\n{thread_context[0]['body']}"
        
        # Generate a baseline AI response (the "bad" example)
        baseline_prompt = f"Based on the following email thread, write a reply."
        baseline_response = await openrouter_service.get_llm_response(
            prompt=context_str, 
            system_prompt=baseline_prompt, 
            model="google/gemini-2.5-flash"
        )
        
        few_shot_examples.append({
            "context": context_str,
            "good_example": user_response['body'],
            "bad_example": baseline_response
        })

    # Final prompt to define the tone
    examples_str = "\n===\n".join([f"CONTEXT:\n{ex['context']}\n\nGOOD RESPONSE (USER):\n{ex['good_example']}\n\nPOOR RESPONSE (GENERIC AI):\n{ex['bad_example']}" for ex in few_shot_examples])
    
    tone_system_prompt = (
        "You are an expert linguistic analyst specializing in individual communication patterns within professional email correspondence. Your task is to analyze a series of emails from a single user and provide a highly specific, nuanced, and actionable tone-of-voice profile."
"Prioritize identifying unique and distinctive characteristics of this user's email communication. Avoid stating generic or obvious observations about email in general (e.g., 'they use subject lines'). Focus on the subtle, recurring elements that would allow someone familiar with this user to immediately recognize an email as theirs, even without seeing the sender's name."
"Your analysis must include:"
"Overall Tone Profile (Highly Specific):"
"Beyond broad categories like 'formal' or 'casual', describe the precise flavor of their tone. Is it briskly efficient, thoughtfully contemplative, gently persuasive, assertively direct, subtly humorous, cautiously optimistic, etc.?"
"Detail any prevalent emotional undertones (e.g., urgency, reassurance, skepticism, enthusiasm, detachment)."
"Note any recurring rhetorical devices or stylistic flourishes (e.g., specific types of hedging, direct addressing of the recipient, use of rhetorical questions, particular forms of emphasis)."
"Specific Behavioral Examples:"
"For every point made in the tone profile, provide concrete, illustrative examples directly quoted or closely paraphrased from the user's emails. These examples are crucial for demonstrating your observations. If the examples are long, provide representative snippets."
"Thoroughness of Response to Facts:"
"Analyze how the user addresses multiple factual points or questions within an incoming email."
"Clearly distinguish between instances where the user explicitly acknowledges or responds to a fact/question, and instances where they omit a response (either intentionally or unintentionally)."
"Quantify, if possible, the proportion of facts/questions addressed versus unaddressed."
"Provide examples of both thorough and less thorough responses regarding factual points."
"General Answer Length and Variation:"
"Describe the typical length of the user's email responses. Is there a default length (e.g., concise, moderately detailed, verbose)?"
"Provide examples of character/word count ranges for typical short, medium, and long responses."
"Tone-Dependent Answer Length and Thoroughness:"
"Analyze whether the user's answer length and thoroughness (regarding factual responses) demonstrably change based on the tone of the incoming email."
"Categorize incoming email tones (e.g., Urgent/Demanding, Casual/Informal, Formal/Inquiry, Challenging/Critical, Collaborative/Supportive, Informational/Neutral)."
"For each identified incoming tone category, describe:"
"How the user's response length typically shifts (e.g., 'When faced with urgent incoming emails, their responses tend to be 20-30% shorter and more direct')."
"How their thoroughness in addressing facts changes (e.g., 'In response to critical emails, they become significantly more meticulous in addressing every point, often breaking them down bullet by bullet')."
"Provide specific examples to illustrate these tone-dependent shifts."
"Make sure that the analysis is in the language of the user."
    )

    # Call LLM to get the final tone profile for the language
    tone_analysis_result = await openrouter_service.get_llm_response(
        prompt=examples_str,
        system_prompt=tone_system_prompt,
        model="google/gemini-2.5-flash"
    )
    
    return tone_analysis_result


async def _analyze_tone_of_voice(emails: List[Dict], user_email: str) -> Dict:
    """
    Analyzes the user's tone of voice from a list of emails.
    """
    # Group emails by language
    emails_by_lang = defaultdict(list)
    for email in emails:
        lang = email.get('language', 'unknown')
        emails_by_lang[lang].append(email)

    final_tone_profile = {}

    for lang, lang_emails in emails_by_lang.items():
        if len(lang_emails) < 10:
            logger.info(f"Skipping tone analysis for language '{lang}' due to insufficient emails ({len(lang_emails)} < 10).")
            continue

        # Group emails by thread
        threads = defaultdict(list)
        for email in lang_emails:
            threads[email['thread_id']].append(email)

        # Filter for messages where the user replies to someone else, creating context/response segments.
        candidate_segments = []
        for thread_id, messages in threads.items():
            # A thread is a list of messages sorted chronologically.
            for i, message in enumerate(messages):
                # We are looking for a message from the user.
                sender = message.get('sender', '')
                if user_email in sender:
                    # This is a user message. Check if it's a reply to someone else.
                    if i > 0:
                        prev_message = messages[i - 1]
                        prev_sender = prev_message.get('sender', '')
                        if user_email not in prev_sender:
                            # This is an "Other -> User" transition.
                            # The context is the single message just before the user's reply.
                            context_messages = [prev_message]
                            user_response_message = message
                            candidate_segments.append({
                                "context": context_messages,
                                "response": user_response_message
                            })

        if not candidate_segments:
             logger.info(f"No suitable candidate segments found for language '{lang}' for tone analysis.")
             continue

        # Select 10 random segments, or fewer if not enough are available.
        num_to_select = min(10, len(candidate_segments))
        selected_segments = random.sample(candidate_segments, num_to_select)
        
        logger.info(f"Selected {len(selected_segments)} segments for language '{lang}' to analyze tone.")

        few_shot_examples = []
        for segment in selected_segments:
            thread_context = segment['context']
            user_response = segment['response'] # The "good" example

            # Format context for the prompt
            context_str = f"From: {thread_context[0]['sender']}\n\n{thread_context[0]['body']}"
            
            # Generate a baseline AI response (the "bad" example)
            baseline_prompt = f"Based on the following email thread, write a reply."
            baseline_response = await openrouter_service.get_llm_response(
                prompt=context_str, 
                system_prompt=baseline_prompt, 
                model="google/gemini-2.5-flash"
            )
            
            few_shot_examples.append({
                "context": context_str,
                "good_example": user_response['body'],
                "bad_example": baseline_response
            })

        # Final prompt to define the tone
        examples_str = "\n===\n".join([f"CONTEXT:\n{ex['context']}\n\nGOOD RESPONSE (USER):\n{ex['good_example']}\n\nPOOR RESPONSE (GENERIC AI):\n{ex['bad_example']}" for ex in few_shot_examples])
        
        tone_system_prompt = (
            "You are an expert linguistic analyst specializing in individual communication patterns within professional email correspondence. Your task is to analyze a series of emails from a single user and provide a highly specific, nuanced, and actionable tone-of-voice profile."
"Prioritize identifying unique and distinctive characteristics of this user's email communication. Avoid stating generic or obvious observations about email in general (e.g., 'they use subject lines'). Focus on the subtle, recurring elements that would allow someone familiar with this user to immediately recognize an email as theirs, even without seeing the sender's name."
"Your analysis must include:"
"Overall Tone Profile (Highly Specific):"
"Beyond broad categories like 'formal' or 'casual', describe the precise flavor of their tone. Is it briskly efficient, thoughtfully contemplative, gently persuasive, assertively direct, subtly humorous, cautiously optimistic, etc.?"
"Detail any prevalent emotional undertones (e.g., urgency, reassurance, skepticism, enthusiasm, detachment)."
"Note any recurring rhetorical devices or stylistic flourishes (e.g., specific types of hedging, direct addressing of the recipient, use of rhetorical questions, particular forms of emphasis)."
"Specific Behavioral Examples:"
"For every point made in the tone profile, provide concrete, illustrative examples directly quoted or closely paraphrased from the user's emails. These examples are crucial for demonstrating your observations. If the examples are long, provide representative snippets."
"Thoroughness of Response to Facts:"
"Analyze how the user addresses multiple factual points or questions within an incoming email."
"Clearly distinguish between instances where the user explicitly acknowledges or responds to a fact/question, and instances where they omit a response (either intentionally or unintentionally)."
"Quantify, if possible, the proportion of facts/questions addressed versus unaddressed."
"Provide examples of both thorough and less thorough responses regarding factual points."
"General Answer Length and Variation:"
"Describe the typical length of the user's email responses. Is there a default length (e.g., concise, moderately detailed, verbose)?"
"Provide examples of character/word count ranges for typical short, medium, and long responses."
"Tone-Dependent Answer Length and Thoroughness:"
"Analyze whether the user's answer length and thoroughness (regarding factual responses) demonstrably change based on the tone of the incoming email."
"Categorize incoming email tones (e.g., Urgent/Demanding, Casual/Informal, Formal/Inquiry, Challenging/Critical, Collaborative/Supportive, Informational/Neutral)."
"For each identified incoming tone category, describe:"
"How the user's response length typically shifts (e.g., 'When faced with urgent incoming emails, their responses tend to be 20-30% shorter and more direct')."
"How their thoroughness in addressing facts changes (e.g., 'In response to critical emails, they become significantly more meticulous in addressing every point, often breaking them down bullet by bullet')."
"Provide specific examples to illustrate these tone-dependent shifts."
"Make sure that the analysis is in the language of the user."
        )

        # Call LLM to get the final tone profile for the language
        tone_analysis_result = await openrouter_service.get_llm_response(
            prompt=examples_str,
            system_prompt=tone_system_prompt,
            model="google/gemini-2.5-flash"
        )
        final_tone_profile[lang] = {
            "profile": tone_analysis_result, 
            "examples_used": len(few_shot_examples),
            "system_prompt": tone_system_prompt,
            "user_prompt": examples_str
        }
    
    return final_tone_profile
