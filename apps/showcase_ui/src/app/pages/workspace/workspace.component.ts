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

import { Component, ChangeDetectionStrategy, NgZone, DestroyRef, inject, computed, signal, ViewChild, ElementRef, OnInit } from '@angular/core';

import { FormsModule } from '@angular/forms';
import { AgentStreamComponent } from '../../components/agent-stream/agent-stream.component';
import { ChatInterfaceComponent } from '../../components/chat-interface/chat-interface.component';
import { FloatingVideoPlayerComponent } from '../../components/floating-video-player/floating-video-player.component';
import { AgentService } from '../../services/agent.service';
import { VoiceInputService } from '../../services/voice-input.service';
import { VoiceSynthesisService } from '../../services/voice-synthesis.service';

@Component({
  selector: 'app-workspace',
  standalone: true,
  imports: [
    FormsModule,
    AgentStreamComponent,
    ChatInterfaceComponent,
    FloatingVideoPlayerComponent
],
  templateUrl: './workspace.component.html',
  styleUrl: './workspace.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class WorkspaceComponent implements OnInit {
  public agentService = inject(AgentService);
  public voiceInput = inject(VoiceInputService);
  public voiceSynthesis = inject(VoiceSynthesisService);
  private zone = inject(NgZone);
  private destroyRef = inject(DestroyRef);

  // Default right panel width to 1/3 of the screen (or 450px as fallback)
  public rightPanelWidth = signal<number>(
    typeof window !== 'undefined' ? Math.round(window.innerWidth / 3) : 450
  );
  public isDragging = signal<boolean>(false);
  private dragWidthRafId: number | null = null;
  private pendingDragWidth = 0;

  // Floating Command Bar State. taskInput is backed by a signal so computed
  // expressions (isBarExpanded) genuinely track it under OnPush.
  private taskInputSignal = signal<string>('');
  public get taskInput(): string { return this.taskInputSignal(); }
  public set taskInput(value: string) { this.taskInputSignal.set(value); }
  public isSubmitting = signal<boolean>(false);
  public errorMessage = signal<string | null>(null);
  public selectedProfile = signal<'flash' | 'pro'>('flash');

  // Security Passphrase State (Masked & Protected)
  public unlockPassphrase = signal<string>('');
  public showPassphraseInput = signal<boolean>(false);
  public isPassphraseMasked = signal<boolean>(true);
  public isPassphraseFocused = signal<boolean>(false);

  public isPassphraseValid(text: string): boolean {
    return !!text && text.trim().length > 0;
  }

  public isPassphraseArmed = computed<boolean>(() => this.isPassphraseValid(this.unlockPassphrase()));

  public togglePassphraseInput(event?: Event): void {
    if (event) {
      event.stopPropagation();
      event.preventDefault();
    }
    this.showPassphraseInput.update(v => !v);
  }

  public togglePassphraseMask(event?: Event): void {
    if (event) {
      event.stopPropagation();
      event.preventDefault();
    }
    this.isPassphraseMasked.update(v => !v);
  }

  public clearPassphrase(event?: Event): void {
    if (event) {
      event.stopPropagation();
      event.preventDefault();
    }
    this.unlockPassphrase.set('');
  }

  public setPassphrase(val: string): void {
    this.unlockPassphrase.set(val);
  }

  // Expand States (Signals for 0-latency reactivity)
  public isHoveringCard = signal<boolean>(false);
  public isInputFocused = signal<boolean>(false);

  @ViewChild('dockInput') public dockInputRef?: ElementRef<HTMLTextAreaElement>;

  ngOnInit(): void {
    if (typeof localStorage !== 'undefined') {
      const saved = localStorage.getItem('artemis_selected_profile');
      if (saved === 'flash' || saved === 'pro') {
        this.selectedProfile.set(saved);
      }
    }

    // The global ⌘K/Ctrl+K shortcut is registered outside the Angular zone so
    // ordinary typing never schedules an extra change-detection pass.
    this.zone.runOutsideAngular(() => {
      window.addEventListener('keydown', this.onGlobalKeyDown);
    });
    this.destroyRef.onDestroy(() => {
      window.removeEventListener('keydown', this.onGlobalKeyDown);
      this.detachDragListeners();
    });
  }

  /**
   * Set agent architecture profile ('flash' vs 'pro')
   */
  public setProfile(profile: 'flash' | 'pro', event?: MouseEvent): void {
    if (event) {
      event.stopPropagation();
    }
    this.selectedProfile.set(profile);
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem('artemis_selected_profile', profile);
    }
  }

  /**
   * Computed boolean whether the currently viewed task is actively running or paused.
   * Only displays the stop/cancel button when inspecting an active task.
   */
  public isTaskRunning = computed(() => {
    return this.agentService.isCurrentSessionRunning();
  });

  /**
   * Dynamic tooltip and label indicating which task will be stopped
   */
  public stopButtonTitle = computed(() => {
    const session = this.agentService.currentSession();
    if (session?.initial_goal) {
      const truncated = session.initial_goal.length > 45
        ? session.initial_goal.substring(0, 42) + '...'
        : session.initial_goal;
      return `Stop current task: "${truncated}"`;
    }
    const curId = this.agentService.currentSessionId();
    if (curId) {
      return `Stop current task (${curId})`;
    }
    return 'Stop current running task';
  });

  /**
   * Computed boolean whether the command bar should be in its expanded state:
   * - Mouse is hovering directly on the command card
   * - Input textarea is focused
   * - User has entered task text (drafting)
   */
  public isBarExpanded = computed(() => {
    return (
      this.isHoveringCard() ||
      this.isInputFocused() ||
      this.isPassphraseFocused() ||
      this.showPassphraseInput() ||
      this.unlockPassphrase().trim().length > 0 ||
      this.taskInput.trim().length > 0
    );
  });

  /**
   * Focus input handler
   */
  public onInputFocus(): void {
    this.isInputFocused.set(true);
  }

  /**
   * Blur input handler
   */
  public onInputBlur(): void {
    this.isInputFocused.set(false);
  }

  /**
   * Click on the resting capsule or dock card to focus textarea
   */
  public onCardClick(event: MouseEvent): void {
    const target = event.target as HTMLElement;
    // Don't steal focus if clicking action buttons, inputs, or passphrase wrap directly
    if (
      target.closest('button') ||
      target.closest('.dock-pass-input-wrap') ||
      target.tagName.toLowerCase() === 'textarea' ||
      target.tagName.toLowerCase() === 'input'
    ) {
      return;
    }
    this.focusInput();
  }

  /**
   * Focus textarea programmatically
   */
  public focusInput(): void {
    setTimeout(() => {
      this.dockInputRef?.nativeElement?.focus();
    }, 30);
  }

  /**
   * Clear typed task input
   */
  public clearInput(event?: MouseEvent): void {
    if (event) {
      event.stopPropagation();
    }
    this.taskInput = '';
    if (this.dockInputRef?.nativeElement) {
      this.dockInputRef.nativeElement.style.height = 'auto';
      this.dockInputRef.nativeElement.focus();
    }
  }

  private keywordDebounceTimer: any = null;

  /**
   * Toggle voice input (microphone) to transcribe spoken instructions
   */
  public toggleVoiceInput(event?: MouseEvent): void {
    if (event) {
      event.stopPropagation();
    }
    if (this.voiceInput.isListening()) {
      this.voiceInput.stopListening();
      if (this.keywordDebounceTimer) {
        clearTimeout(this.keywordDebounceTimer);
        this.keywordDebounceTimer = null;
      }
      return;
    }

    this.voiceInput.startListening(this.taskInput, (fullText) => {
      // Check if user spoken text matches current entered passphrase
      const currentPass = this.unlockPassphrase().trim();
      if (currentPass && fullText.toLowerCase().includes(currentPass.toLowerCase())) {
        const cleaned = fullText.replace(new RegExp(currentPass, 'gi'), '').trim();
        this.taskInput = cleaned || 'Unlock phone and go to home screen';

        if (this.keywordDebounceTimer) {
          clearTimeout(this.keywordDebounceTimer);
        }
        this.keywordDebounceTimer = setTimeout(() => {
          this.voiceInput.stopListening();
          this.voiceSynthesis.speak('Voice authorization confirmed. Unlocking phone.');
          this.submitTask();
          this.keywordDebounceTimer = null;
        }, 650);
        return;
      }

      this.taskInput = fullText;
      if (this.dockInputRef?.nativeElement) {
        this.dockInputRef.nativeElement.style.height = 'auto';
        const newHeight = Math.min(Math.max(this.dockInputRef.nativeElement.scrollHeight, 24), 120);
        this.dockInputRef.nativeElement.style.height = `${newHeight}px`;
      }
    });
  }

  /**
   * Auto-resize textarea as user types multi-line tasks & stealth-mask secret words
   */
  public onTextareaInput(event: Event): void {
    const textarea = event.target as HTMLTextAreaElement;
    if (!textarea) return;

    // Check for secret passphrase in real-time typing against current entered passphrase
    const raw = textarea.value;
    const currentPass = this.unlockPassphrase().trim();
    if (currentPass && raw.toLowerCase().includes(currentPass.toLowerCase())) {
      const cleaned = raw.replace(new RegExp(currentPass, 'gi'), '').trim();
      textarea.value = cleaned;
      this.taskInput = cleaned;
    }

    textarea.style.height = 'auto';
    const newHeight = Math.min(Math.max(textarea.scrollHeight, 24), 120);
    textarea.style.height = `${newHeight}px`;
  }

  /**
   * Global keyboard shortcut (⌘K or Ctrl+K) to focus input bar from anywhere
   */
  private onGlobalKeyDown = (event: KeyboardEvent): void => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      this.focusInput();
    }
  };

  /**
   * Handle enter key in floating dock textarea
   */
  public onKeyDown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.submitTask();
    }
  }

  /**
   * Submit a new task instruction
   */
  public submitTask(): void {
    const hasValidPass = this.isPassphraseValid(this.unlockPassphrase());
    let goal = this.taskInput.trim();
    if (!goal && hasValidPass) {
      goal = 'confirm device is unlocked on home screen';
    }
    if (!goal || this.isSubmitting()) {
      return;
    }

    this.isSubmitting.set(true);
    this.errorMessage.set(null);

    if (this.dockInputRef?.nativeElement) {
      this.dockInputRef.nativeElement.blur();
    }
    this.isInputFocused.set(false);

    this.agentService.runTask(
      goal,
      this.selectedProfile(),
      undefined,
      undefined,
      undefined,
      this.unlockPassphrase().trim() || undefined
    ).subscribe({
      next: (res) => {
        this.taskInput = '';
        this.unlockPassphrase.set('');
        if (this.dockInputRef?.nativeElement) {
          this.dockInputRef.nativeElement.style.height = 'auto';
        }
        this.isSubmitting.set(false);
        this.agentService.fetchStatus();
      },
      error: (err) => {
        console.error('Failed to submit task:', err);
        this.isSubmitting.set(false);
        const detail = err.error?.detail || 'The runner is busy. Please wait for current task to finish.';
        this.errorMessage.set(detail);
        this.voiceSynthesis.speak(detail);
        setTimeout(() => {
          this.errorMessage.set(null);
        }, 6000);
      }
    });
  }

  /**
   * Stop currently viewed task
   */
  public stopTask(event?: MouseEvent): void {
    if (event) {
      event.stopPropagation();
    }
    if (!this.isTaskRunning()) {
      return;
    }
    const targetSessionId = this.agentService.currentSessionId();
    this.isSubmitting.set(true);
    this.errorMessage.set(null);
    this.agentService.stopTask(targetSessionId, false);
    setTimeout(() => {
      this.isSubmitting.set(false);
    }, 400);
  }

  /**
   * Handle mouse down on resizer bar to start dragging. The move/up listeners
   * are attached only for the duration of the drag and run outside the Angular
   * zone: idle mouse movement over the workspace never triggers change
   * detection, and drag updates are coalesced to one per animation frame.
   */
  public onDragStart(event: MouseEvent): void {
    this.isDragging.set(true);
    event.preventDefault();
    this.zone.runOutsideAngular(() => {
      document.addEventListener('mousemove', this.onMouseMove);
      document.addEventListener('mouseup', this.onMouseUp);
    });
  }

  private onMouseMove = (event: MouseEvent): void => {
    if (!this.isDragging()) {
      return;
    }

    const newWidth = window.innerWidth - event.clientX;
    const minWidth = 250;
    const maxWidth = window.innerWidth - 300;

    // Apply boundary limits to prevent panels from shrinking too much
    if (newWidth >= minWidth && newWidth <= maxWidth) {
      this.pendingDragWidth = newWidth;
      if (this.dragWidthRafId === null) {
        this.dragWidthRafId = requestAnimationFrame(() => {
          this.dragWidthRafId = null;
          this.rightPanelWidth.set(this.pendingDragWidth);
        });
      }
    }
  };

  private onMouseUp = (): void => {
    this.isDragging.set(false);
    this.detachDragListeners();
  };

  private detachDragListeners(): void {
    document.removeEventListener('mousemove', this.onMouseMove);
    document.removeEventListener('mouseup', this.onMouseUp);
    if (this.dragWidthRafId !== null) {
      cancelAnimationFrame(this.dragWidthRafId);
      this.dragWidthRafId = null;
    }
  }
}
