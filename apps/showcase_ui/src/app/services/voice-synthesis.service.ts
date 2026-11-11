/**
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import { Injectable, NgZone, inject, signal } from '@angular/core';

@Injectable({
  providedIn: 'root'
})
export class VoiceSynthesisService {
  private zone = inject(NgZone);
  private synthesis: SpeechSynthesis | null = null;
  private selectedVoice: SpeechSynthesisVoice | null = null;

  public isSpeaking = signal<boolean>(false);
  public isEnabled = signal<boolean>(true);
  public isSupported = signal<boolean>(false);

  constructor() {
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      this.synthesis = window.speechSynthesis;
      this.isSupported.set(true);

      const saved = localStorage.getItem('artemis_voice_speech_enabled');
      if (saved !== null) {
        this.isEnabled.set(saved === 'true');
      }

      this.initVoices();
      if (this.synthesis.onvoiceschanged !== undefined) {
        this.synthesis.onvoiceschanged = () => {
          this.initVoices();
        };
      }
    }
  }

  private initVoices(): void {
    if (!this.synthesis) return;
    const voices = this.synthesis.getVoices();
    if (!voices || voices.length === 0) return;

    // Prefer high-quality English natural voices
    const preferredNames = [
      'google us english',
      'natural',
      'samantha',
      'jenny',
      'guy',
      'aria',
      'david',
      'zira',
      'daniel'
    ];

    let match = voices.find((v) =>
      preferredNames.some((p) => v.name.toLowerCase().includes(p) && v.lang.startsWith('en'))
    );

    if (!match) {
      match = voices.find((v) => v.lang.startsWith('en') && v.default) || voices.find((v) => v.lang.startsWith('en'));
    }

    if (match) {
      this.selectedVoice = match;
    }
  }

  /**
   * Speak out text with clean speech synthesis.
   */
  public speak(
    rawText: string,
    options?: { priority?: boolean; rate?: number; pitch?: number }
  ): void {
    if (!this.synthesis || !this.isEnabled()) return;

    const cleaned = this.cleanForSpeech(rawText);
    if (!cleaned) return;

    if (options?.priority || this.isSpeaking()) {
      this.stop();
    }

    try {
      const utterance = new SpeechSynthesisUtterance(cleaned);
      if (this.selectedVoice) {
        utterance.voice = this.selectedVoice;
      }
      utterance.rate = options?.rate ?? 1.05;
      utterance.pitch = options?.pitch ?? 1.0;
      utterance.lang = this.selectedVoice?.lang || 'en-US';

      utterance.onstart = () => {
        this.zone.run(() => {
          this.isSpeaking.set(true);
        });
      };

      utterance.onend = () => {
        this.zone.run(() => {
          this.isSpeaking.set(false);
        });
      };

      utterance.onerror = (e) => {
        this.zone.run(() => {
          this.isSpeaking.set(false);
        });
      };

      this.synthesis.speak(utterance);
    } catch (err) {
      console.warn('Speech synthesis error:', err);
      this.isSpeaking.set(false);
    }
  }

  /**
   * Cancel and stop any ongoing speech.
   */
  public stop(): void {
    if (this.synthesis) {
      try {
        this.synthesis.cancel();
      } catch (err) {
        // ignore
      }
      this.isSpeaking.set(false);
    }
  }

  /**
   * Toggle voice narration on / off.
   */
  public toggleVoice(): boolean {
    const nextState = !this.isEnabled();
    this.isEnabled.set(nextState);
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem('artemis_voice_speech_enabled', String(nextState));
    }
    if (nextState) {
      this.speak('Artemis voice enabled.');
    } else {
      this.stop();
    }
    return nextState;
  }

  /**
   * Cleans text to produce natural, smooth sounding speech without markdown or code.
   */
  private cleanForSpeech(text: string): string {
    if (!text) return '';
    return text
      .replace(/```[\s\S]*?```/g, '') // remove code blocks
      .replace(/`([^`]+)`/g, '$1') // remove inline code ticks
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1') // markdown links -> title
      .replace(/https?:\/\/\S+/g, 'link') // URLs -> 'link'
      .replace(/[*_~#>]/g, '') // bold/italic/header symbols
      .replace(/[{}\[\]\\\/]/g, ' ') // curly braces/brackets
      .replace(/\s+/g, ' ') // excessive spaces
      .trim();
  }
}
