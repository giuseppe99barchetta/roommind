import { css } from "lit";

/** Read-only equipment rows; edit forms retain their existing layout. */
export const equipmentStyles = css`
  .equipment-view {
    display: grid;
    gap: 16px;
  }
  .equipment-view .section-subtitle {
    margin: 0 0 10px;
    text-transform: none;
    letter-spacing: 0;
    font-size: 12px;
    font-weight: 600;
    color: var(--secondary-text-color);
  }
  .equipment-view .device-group {
    padding: 0;
    margin: 0;
    border: 0;
  }
  .equipment-view .view-row {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
    padding: 12px;
    margin-top: 6px;
    border: 1px solid var(--divider-color, rgba(128, 128, 128, 0.16));
    border-radius: 12px;
    background: var(--secondary-background-color, rgba(128, 128, 128, 0.05));
    min-width: 0;
  }
  .equipment-view .view-icon {
    --mdc-icon-size: 20px;
    display: grid;
    place-items: center;
    width: 34px;
    height: 34px;
    border-radius: 10px;
    color: var(--primary-color);
    background: var(--card-background-color);
    flex-shrink: 0;
  }
  .equipment-view .view-name {
    flex: 1;
    min-width: 70px;
    font: inherit;
    font-size: 13px;
    line-height: 1.45;
    color: var(--primary-text-color);
    white-space: normal;
    overflow-wrap: anywhere;
    text-align: start;
  }
  .equipment-view button.view-name {
    padding: 0;
    border: 0;
    background: none;
    cursor: pointer;
  }
  .equipment-view button:focus-visible {
    outline: 2px solid var(--primary-color);
    outline-offset: 4px;
    border-radius: 4px;
  }
  .equipment-view .view-value {
    font-size: 16px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    margin-inline-start: auto;
  }
  .equipment-view .delay-view {
    padding: 8px 2px 0;
    font-size: 12px;
    line-height: 1.6;
  }
  .equipment-view .sensor-state {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    color: var(--secondary-text-color);
    font-size: 12px;
  }
  .equipment-view .equipment-edit {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    justify-self: start;
    min-height: 36px;
    padding: 6px 2px;
    border: 0;
    background: none;
    color: var(--primary-color);
    font: inherit;
    font-size: 12px;
    cursor: pointer;
  }
  .equipment-edit ha-icon {
    --mdc-icon-size: 16px;
  }
  .equipment-empty {
    margin: 0;
    color: var(--secondary-text-color);
    font-size: 13px;
    line-height: 1.6;
  }
`;
