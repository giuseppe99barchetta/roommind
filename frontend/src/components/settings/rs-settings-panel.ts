/**
 * rs-settings-panel – Reusable accordion panel for settings sections.
 * Wraps ha-expansion-panel with icon, title, optional badge, and intro text.
 */
import { LitElement, html, css, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import "../shared/rs-badge";

@customElement("rs-settings-panel")
export class RsSettingsPanel extends LitElement {
  @property({ type: String }) public icon = "";
  @property({ type: String }) public heading = "";
  @property({ type: String }) public intro = "";
  @property({ type: String }) public badge = "";
  @property({ type: String }) public badgeHint = "";

  render() {
    return html`
      <ha-expansion-panel outlined>
        <div slot="header" class="panel-header">
          <ha-icon .icon=${this.icon}></ha-icon>
          <span>${this.heading}</span>
          ${this.badge
            ? html`<rs-badge .label=${this.badge} .hint=${this.badgeHint}></rs-badge>`
            : nothing}
        </div>
        <div class="panel-content">
          ${this.intro ? html`<p class="section-intro">${this.intro}</p>` : nothing}
          <slot></slot>
        </div>
      </ha-expansion-panel>
    `;
  }

  static styles = css`
    :host {
      display: block;
    }
    :host([hidden]) { display: none !important; }
    ha-expansion-panel { --ha-card-border-radius: 16px; --ha-card-box-shadow: none; }

    .panel-header {
      display: flex;
      align-items: center;
      gap: 13px;
      min-height: 44px;
      --mdc-icon-size: 20px;
      color: var(--primary-color, var(--secondary-text-color));
    }

    .panel-header span {
      color: var(--primary-text-color);
      font-weight: 650;
      font-size: 14px;
    }

    .panel-content {
      padding: 12px 20px 22px;
    }

    .section-intro {
      color: var(--secondary-text-color);
      font-size: 13px;
      line-height: 1.5;
      margin: 0 0 16px;
      padding: 0;
    }
  `;
}

declare global {
  interface HTMLElementTagNameMap {
    "rs-settings-panel": RsSettingsPanel;
  }
}
