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

import { Component, ChangeDetectionStrategy, inject } from '@angular/core';

import { RouterLink, RouterLinkActive } from '@angular/router';
import { VoiceSynthesisService } from '../../services/voice-synthesis.service';

@Component({
  selector: 'app-nav-switcher',
  standalone: true,
  imports: [RouterLink, RouterLinkActive],
  template: `
    <nav class="floating-nav-switcher" aria-label="Main Navigation">
      <a 
        routerLink="/" 
        routerLinkActive="active" 
        [routerLinkActiveOptions]="{exact: true}"
        class="nav-tab-btn"
        title="Return to Home Launcher to start a new task"
      >
        <span class="material-symbols-outlined tab-icon">add_task</span>
        <span class="tab-label">New / Home</span>
      </a>
      <a 
        routerLink="/workspace" 
        routerLinkActive="active" 
        class="nav-tab-btn"
        title="Open Workspace"
      >
        <span class="material-symbols-outlined tab-icon">space_dashboard</span>
        <span class="tab-label">Workspace</span>
      </a>
      <div class="nav-divider"></div>
      <button
        type="button"
        class="nav-voice-btn"
        [class.is-speaking]="voiceSynthesis.isSpeaking()"
        [class.is-muted]="!voiceSynthesis.isEnabled()"
        (click)="voiceSynthesis.toggleVoice()"
        [title]="voiceSynthesis.isEnabled() ? (voiceSynthesis.isSpeaking() ? 'Artemis is speaking... (click to mute)' : 'Artemis Voice ON (click to mute)') : 'Artemis Voice Muted (click to enable)'"
        aria-label="Toggle Artemis Voice"
      >
        <span class="material-symbols-outlined voice-icon">
          {{ !voiceSynthesis.isEnabled() ? 'volume_off' : (voiceSynthesis.isSpeaking() ? 'record_voice_over' : 'volume_up') }}
        </span>
        <span class="voice-label">
          {{ !voiceSynthesis.isEnabled() ? 'Muted' : (voiceSynthesis.isSpeaking() ? 'Speaking...' : 'Voice') }}
        </span>
      </button>
    </nav>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrls: ['./nav-switcher.component.scss']
})
export class NavSwitcherComponent {
  public voiceSynthesis = inject(VoiceSynthesisService);
}
