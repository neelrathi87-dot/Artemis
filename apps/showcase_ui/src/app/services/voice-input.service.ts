import { Injectable, NgZone, inject, signal } from '@angular/core';

@Injectable({
  providedIn: 'root'
})
export class VoiceInputService {
  private zone = inject(NgZone);
  private recognition: any = null;

  public isListening = signal<boolean>(false);
  public isSupported = signal<boolean>(false);
  public error = signal<string | null>(null);

  private baseText = '';
  private onUpdateCallback?: (text: string) => void;

  constructor() {
    if (typeof window !== 'undefined') {
      const SpeechRecognition =
        (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      this.isSupported.set(!!SpeechRecognition);
    }
  }

  /**
   * Starts listening to user speech and streams transcription.
   * If already listening, stops the session.
   */
  public toggleListening(
    currentText: string,
    onUpdate: (fullText: string) => void,
    onError?: (msg: string) => void
  ): void {
    if (this.isListening()) {
      this.stopListening();
    } else {
      this.startListening(currentText, onUpdate, onError);
    }
  }

  public startListening(
    initialText: string,
    onUpdate: (fullText: string) => void,
    onError?: (msg: string) => void
  ): boolean {
    if (typeof window === 'undefined') return false;

    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      const msg = 'Speech recognition is not supported in this browser. Please use Chrome or Edge.';
      this.error.set(msg);
      onError?.(msg);
      return false;
    }

    this.stopListening();

    try {
      this.recognition = new SpeechRecognition();
      this.recognition.continuous = true;
      this.recognition.interimResults = true;
      this.recognition.lang = typeof navigator !== 'undefined' ? (navigator.language || 'en-US') : 'en-US';

      this.baseText = initialText.trim();
      this.onUpdateCallback = onUpdate;
      this.error.set(null);

      this.recognition.onstart = () => {
        this.zone.run(() => {
          this.isListening.set(true);
        });
      };

      this.recognition.onresult = (event: any) => {
        this.zone.run(() => {
          let fullSpeech = '';
          for (let i = 0; i < event.results.length; ++i) {
            fullSpeech += event.results[i][0].transcript;
          }
          const spoken = fullSpeech.trim();
          const combined = this.baseText ? `${this.baseText} ${spoken}` : spoken;
          this.onUpdateCallback?.(combined);
        });
      };

      this.recognition.onerror = (event: any) => {
        this.zone.run(() => {
          console.warn('Voice input error:', event.error);
          let errText = '';
          if (event.error === 'not-allowed') {
            errText = 'Microphone permission denied. Please allow microphone access.';
          } else if (event.error === 'no-speech') {
            // benign, no speech detected
            return;
          } else {
            errText = `Voice input error: ${event.error}`;
          }
          this.error.set(errText);
          onError?.(errText);
          this.isListening.set(false);
        });
      };

      this.recognition.onend = () => {
        this.zone.run(() => {
          this.isListening.set(false);
        });
      };

      this.recognition.start();
      return true;
    } catch (err: any) {
      this.zone.run(() => {
        console.error('Failed to start voice recognition:', err);
        const msg = 'Could not access microphone.';
        this.error.set(msg);
        onError?.(msg);
        this.isListening.set(false);
      });
      return false;
    }
  }

  public stopListening(): void {
    if (this.recognition) {
      try {
        this.recognition.stop();
      } catch {}
      this.recognition = null;
    }
    this.isListening.set(false);
  }
}
