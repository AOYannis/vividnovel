"""Sequence logger — writes detailed JSON logs for debugging.

Each sequence overwrites the log file, keeping only the latest run.
Also provides a pretty console printer.
"""
import json
import time
import os
from datetime import datetime

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "last_sequence.json")


class SequenceLogger:
    """Collects events during a sequence and writes them to a JSON file."""

    def __init__(self, session_id: str, sequence_number: int, grok_model: str):
        self.session_id = session_id
        self.sequence_number = sequence_number
        self.grok_model = grok_model
        self.start_time = time.time()
        self.events: list[dict] = []
        self._print(f"{'='*60}")
        self._print(f"SEQUENCE {sequence_number} | model={grok_model} | session={session_id[:8]}...")

    def _print(self, msg: str):
        print(f"[seq {self.sequence_number}] {msg}")

    def _add(self, event_type: str, data: dict):
        entry = {
            "time": round(time.time() - self.start_time, 2),
            "type": event_type,
            **data,
        }
        self.events.append(entry)

    def log_mem0_recall(self, memory_type: str, content: str):
        """Log a mem0 recall (narrative or persistent)."""
        lines = [l.strip() for l in content.strip().split("\n") if l.strip().startswith("- ")]
        self._print(f"MEM0 RECALL ({memory_type}): {len(lines)} facts, {len(content)} chars")
        for line in lines[:5]:
            self._print(f"  {line[:100]}{'...' if len(line) > 100 else ''}")
        if len(lines) > 5:
            self._print(f"  ... and {len(lines) - 5} more")
        self._add("mem0_recall", {
            "memory_type": memory_type,
            "fact_count": len(lines),
            "content_length": len(content),
            "facts": [l.lstrip("- ") for l in lines],
            "raw": content,
        })

    def log_mem0_store(self, narration_length: int, choice: str | None):
        """Log a mem0 store operation."""
        self._print(f"MEM0 STORE: narration={narration_length} chars | choice={choice[:50] if choice else 'none'}")
        self._add("mem0_store", {
            "narration_length": narration_length,
            "choice": choice,
        })

    def log_system_prompt(self, prompt_length: int, has_persistent_memory: bool, has_narrative_memory: bool):
        self._print(f"System prompt: {prompt_length} chars | "
                     f"mem0_persistent={'YES' if has_persistent_memory else 'no'} | "
                     f"mem0_narrative={'YES' if has_narrative_memory else 'no'}")
        self._add("system_prompt", {
            "length": prompt_length,
            "has_persistent_memory": has_persistent_memory,
            "has_narrative_memory": has_narrative_memory,
        })

    def log_messages(self, messages: list[dict]):
        """Log the initial messages sent to Grok."""
        msg_summary = []
        for m in messages:
            role = m.get("role", "?")
            content = m.get("content", "")
            length = len(content) if content else 0
            has_tools = bool(m.get("tool_calls"))
            msg_summary.append({"role": role, "length": length, "has_tool_calls": has_tools})
        self._print(f"Messages to Grok: {len(messages)} messages")
        self._add("grok_request", {"message_count": len(messages), "messages": msg_summary})

    def log_grok_round(self, round_num: int, narration_length: int, tool_calls: list[str]):
        tools_str = ", ".join(tool_calls) if tool_calls else "none"
        self._print(f"Round {round_num}: narration={narration_length} chars | tools=[{tools_str}]")
        self._add("grok_round", {
            "round": round_num,
            "narration_length": narration_length,
            "tool_calls": tool_calls,
        })

    def log_image_request(self, index: int, prompt: str, actors: list[str],
                          moods: list[str], secondary_chars: dict):
        prompt_preview = prompt[:120] + "..." if len(prompt) > 120 else prompt
        self._print(f"  IMAGE {index}: moods={moods} | actors={actors} | prompt={prompt_preview}")
        if secondary_chars:
            self._print(f"    secondary_chars: {list(secondary_chars.keys())}")
        self._add("image_request", {
            "index": index,
            "prompt": prompt,
            "prompt_length": len(prompt),
            "actors_present": actors,
            "style_moods": moods,
            "secondary_characters": secondary_chars,
        })

    def log_image_prompt_crafted(self, index: int, scene_summary: str,
                                  shot_intent: str, mood: str,
                                  actors: list[str], final_prompt: str,
                                  elapsed: float):
        """Audit how the image-prompt specialist (Phase 3A) transformed the
        narrator's lean scene spec into the final Z-Image prompt."""
        self._print(
            f"  PROMPT-CRAFT {index}: mood={mood} actors={actors} "
            f"summary={scene_summary[:60]!r} intent={shot_intent[:40]!r} "
            f"final={len(final_prompt)} chars in {elapsed}s"
        )
        self._add("image_prompt_crafted", {
            "index": index,
            "scene_summary": scene_summary,
            "shot_intent": shot_intent,
            "mood": mood,
            "actors_present": actors,
            "final_prompt": final_prompt,
            "final_prompt_length": len(final_prompt),
            "elapsed": elapsed,
        })

    def log_image_result(self, index: int, loras_applied: list[dict],
                         final_prompt: str, width: int, height: int,
                         steps: int, cfg: float, seed: int | None,
                         cost: float, elapsed: float):
        lora_names = [f"{l.get('id','?')}@{l.get('weight','?')}" for l in loras_applied]
        self._print(f"  IMAGE {index} DONE: {elapsed}s | ${cost:.4f} | "
                     f"loras=[{', '.join(lora_names)}] | {width}x{height} steps={steps}")
        self._add("image_result", {
            "index": index,
            "loras_applied": loras_applied,
            "final_prompt": final_prompt,
            "width": width,
            "height": height,
            "steps": steps,
            "cfg": cfg,
            "seed": seed,
            "cost": cost,
            "elapsed": elapsed,
        })

    def log_davinci_request(self, index: int, davinci_prompt: str, image_url: str, seed: int | None):
        self._print(f"  DAVINCI {index}: prompt={davinci_prompt[:120]}...")
        self._add("davinci_request", {
            "index": index,
            "davinci_prompt": davinci_prompt,
            "image_url": image_url,
            "seed": seed,
        })

    def log_video_request(self, prompt: str, input_image_index: int):
        self._print(f"  VIDEO: prompt={prompt[:80]}...")
        self._add("video_request", {"prompt": prompt, "input_image_index": input_image_index})

    def log_tts_request(self, scene_index: int, voice: str, language: str,
                         text_length: int, dialogue_only: bool, for_video_only: bool,
                         enhance: bool, stereo: bool):
        self._print(f"  TTS req scene={scene_index} voice={voice} lang={language} "
                     f"chars={text_length} dlg_only={dialogue_only} for_video={for_video_only} enh={enhance} stereo={stereo}")
        self._add("tts_request", {
            "scene_index": scene_index, "voice": voice, "language": language,
            "text_length": text_length, "dialogue_only": dialogue_only,
            "for_video_only": for_video_only, "enhance": enhance, "stereo": stereo,
        })

    def log_tts_result(self, scene_index: int, audio_url: str, char_count: int,
                        cost: float, elapsed: float, enhance_elapsed: float,
                        enhanced_text: str | None = None, backend: str | None = None):
        self._print(f"  TTS done scene={scene_index} backend={backend or '?'} url={audio_url[:60]}... "
                     f"chars={char_count} cost=${cost:.4f} tts={elapsed}s enh={enhance_elapsed}s")
        self._add("tts_result", {
            "scene_index": scene_index, "audio_url": audio_url, "char_count": char_count,
            "cost": cost, "elapsed": elapsed, "enhance_elapsed": enhance_elapsed,
            "enhanced_text": (enhanced_text[:600] if enhanced_text else None),
            "backend": backend,
        })

    def log_tts_error(self, scene_index: int, error: str):
        self._print(f"  TTS ERROR scene={scene_index}: {error}")
        self._add("tts_error", {"scene_index": scene_index, "error": error})

    def log_video_result(self, cost: float, elapsed: float):
        self._print(f"  VIDEO DONE: {elapsed}s | ${cost:.4f}")
        self._add("video_result", {"cost": cost, "elapsed": elapsed})

    def log_choices(self, choices: list[dict]):
        for c in choices:
            self._print(f"  CHOICE {c.get('id','?')}: {c.get('text','')[:60]}")
        self._add("choices", {"choices": choices})

    def log_narration(self, segments: list[str]):
        for i, s in enumerate(segments):
            if s:
                self._print(f"  NARRATION {i}: {s[:80]}{'...' if len(s) > 80 else ''}")
        self._add("narration_segments", {
            "segments": [{"index": i, "length": len(s), "preview": s[:150]} for i, s in enumerate(segments)],
        })

    def log_costs(self, grok_cost: float, image_cost: float, video_cost: float,
                  total: float, input_tokens: int, output_tokens: int, elapsed: float,
                  cached_tokens: int = 0,
                  tts_cost: float = 0.0,
                  tts_audio_cost: float = 0.0,
                  tts_enhance_cost: float = 0.0):
        cache_pct = (100 * cached_tokens / input_tokens) if input_tokens else 0
        self._print(
            f"COSTS: grok=${grok_cost:.4f} ({input_tokens}in/{cached_tokens}cached={cache_pct:.0f}%/{output_tokens}out) | "
            f"images=${image_cost:.4f} | video=${video_cost:.4f} | "
            f"tts=${tts_cost:.4f} (audio=${tts_audio_cost:.4f} + enhance=${tts_enhance_cost:.4f}) | "
            f"TOTAL=${total:.4f} | {elapsed}s"
        )
        self._add("costs", {
            "grok_cost": grok_cost,
            "grok_input_tokens": input_tokens,
            "grok_cached_tokens": cached_tokens,
            "grok_cache_hit_pct": round(cache_pct, 1),
            "grok_output_tokens": output_tokens,
            "image_cost": image_cost,
            "video_cost": video_cost,
            "tts_cost": tts_cost,
            "tts_audio_cost": tts_audio_cost,
            "tts_enhance_cost": tts_enhance_cost,
            "total": total,
            "elapsed_seconds": elapsed,
        })

    def log_error(self, error: str):
        self._print(f"ERROR: {error}")
        self._add("error", {"message": error})

    def finish(self):
        """Write the full log to disk."""
        total_time = round(time.time() - self.start_time, 1)
        self._print(f"{'='*60} ({total_time}s total)")

        log_data = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "sequence_number": self.sequence_number,
            "grok_model": self.grok_model,
            "total_time_seconds": total_time,
            "events": self.events,
        }

        try:
            # Also append to the combined log
            combined_log = os.path.join(LOG_DIR, "session_log.jsonl")
            with open(combined_log, "a") as f:
                f.write(json.dumps(log_data, ensure_ascii=False) + "\n")
        except Exception:
            pass

        try:
            with open(LOG_FILE, "w") as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False)
            self._print(f"Log written to {LOG_FILE}")
        except Exception as e:
            self._print(f"Failed to write log: {e}")


CHAT_LOG_FILE = os.path.join(LOG_DIR, "scene_chats.jsonl")


class ChatLogger:
    """Logs scene chat interactions to a JSONL file (appends, never overwrites)."""

    def __init__(self, session_id: str, scene_index: int, grok_model: str):
        self.session_id = session_id
        self.scene_index = scene_index
        self.grok_model = grok_model
        self.start_time = time.time()
        self.data: dict = {
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "scene_index": scene_index,
            "grok_model": grok_model,
        }
        print(f"[chat s{scene_index}] Starting scene chat (model={grok_model})")

    def log_request(self, player_message: str, actors: list[str],
                    char_memories: str, original_moods: list[str]):
        print(f"[chat s{self.scene_index}] Player: {player_message[:80]}")
        if char_memories:
            lines = char_memories.strip().count("\n") + 1
            print(f"[chat s{self.scene_index}] Character memories: {lines} facts")
        self.data["player_message"] = player_message
        self.data["actors_present"] = actors
        self.data["char_memories_length"] = len(char_memories)
        self.data["original_moods"] = original_moods

    def log_response(self, narration: str, image_change: str, new_mood: str):
        print(f"[chat s{self.scene_index}] Narrator: {narration[:80]}...")
        print(f"[chat s{self.scene_index}] IMAGE_CHANGE: {image_change[:80]}")
        print(f"[chat s{self.scene_index}] MOOD: {new_mood or '(same as original)'}")
        self.data["narration_response"] = narration
        self.data["image_change"] = image_change
        self.data["new_mood"] = new_mood

    def log_image(self, prompt: str, moods: list[str], loras: list[dict],
                  seed: int | None, cost: float, elapsed: float):
        lora_names = [f"{l.get('id','?')}@{l.get('weight','?')}" for l in loras]
        print(f"[chat s{self.scene_index}] IMAGE: moods={moods} | loras=[{', '.join(lora_names)}] | "
              f"${cost:.4f} | {elapsed}s | seed={seed}")
        self.data["image"] = {
            "adapted_prompt": prompt,
            "moods": moods,
            "loras": loras,
            "seed": seed,
            "cost": cost,
            "elapsed": elapsed,
        }

    def log_error(self, error: str):
        print(f"[chat s{self.scene_index}] ERROR: {error}")
        self.data["error"] = error

    def finish(self):
        elapsed = round(time.time() - self.start_time, 1)
        self.data["total_time"] = elapsed
        print(f"[chat s{self.scene_index}] Done ({elapsed}s)")
        try:
            with open(CHAT_LOG_FILE, "a") as f:
                f.write(json.dumps(self.data, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[chat] Failed to write log: {e}")
