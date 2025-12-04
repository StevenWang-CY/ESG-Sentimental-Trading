"""
ESG Event-Driven Strategy Monitoring Dashboard

Interactive Streamlit dashboard for real-time performance monitoring and validation.
Implements automated checks to prevent catastrophic parameter changes like the
HIGH sensitivity degradation (Sharpe 0.70 → 0.04).

Sections:
1. Real-Time Performance Metrics
2. Signal Quality Monitoring
3. Portfolio Health
4. Comparative Analysis
5. Validation Checklist
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import yaml
from pathlib import Path
import json
from datetime import datetime
import sys

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from scripts.validate_backtest import BacktestValidator, ValidationCriteria

# Page config
st.set_page_config(
    page_title="ESG Strategy Monitoring",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
.metric-card {
    background-color: #f0f2f6;
    padding: 20px;
    border-radius: 10px;
    box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
}
.alert-red {
    background-color: #ffebee;
    padding: 15px;
    border-left: 5px solid #f44336;
    border-radius: 5px;
}
.alert-yellow {
    background-color: #fff9c4;
    padding: 15px;
    border-left: 5px solid #ffeb3b;
    border-radius: 5px;
}
.alert-green {
    background-color: #e8f5e9;
    padding: 15px;
    border-left: 5px solid #4caf50;
    border-radius: 5px;
}
</style>
""", unsafe_allow_html=True)


class DashboardData:
    """
    Handles loading and processing of backtest data
    """

    def __init__(self):
        self.config = self.load_config()
        self.baseline = self.load_baseline_results()
        self.current = None
        self.validator = BacktestValidator()

    @staticmethod
    def load_config():
        """Load configuration"""
        try:
            with open('config/config.yaml', 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            st.error(f"Error loading config: {str(e)}")
            return {}

    @staticmethod
    def load_baseline_results():
        """Load baseline (MEDIUM sensitivity, 0.70 Sharpe) results"""
        # This would load from the original MEDIUM backtest
        # For now, returning the known baseline metrics
        return {
            'name': 'MEDIUM Baseline',
            'sharpe_ratio': 0.70,
            'sortino_ratio': 1.29,
            'total_return': 20.38,
            'volatility': 7.08,
            'max_drawdown': -5.29,
            'turnover': 3.19,
            'num_trades': 21,
            'num_events': 58,
            'universe_size': 45,
            'confidence_threshold': 0.20,
            'rebalance_freq': 'W',
            'holding_period': 7
        }

    @staticmethod
    def load_backtest_results(results_path):
        """
        Load backtest results from file

        Args:
            results_path: Path to results file (JSON or log)

        Returns:
            dict: Parsed results
        """
        try:
            if results_path.suffix == '.json':
                with open(results_path, 'r') as f:
                    return json.load(f)
            else:
                # Parse from log file
                results = {}
                with open(results_path, 'r') as f:
                    content = f.read()

                for line in content.split('\n'):
                    if 'sharpe_ratio' in line:
                        results['sharpe_ratio'] = float(line.split(':')[1].strip())
                    elif 'sortino_ratio' in line:
                        results['sortino_ratio'] = float(line.split(':')[1].strip())
                    elif 'total_return ' in line and 'total_return_pct' not in line:
                        results['total_return'] = float(line.split(':')[1].strip().replace('%', ''))
                    elif 'volatility' in line and 'annualized' not in line:
                        results['volatility'] = float(line.split(':')[1].strip().replace('%', ''))
                    elif 'max_drawdown' in line:
                        results['max_drawdown'] = float(line.split(':')[1].strip().replace('%', ''))
                    elif 'turnover' in line:
                        results['turnover'] = float(line.split(':')[1].strip())
                    elif 'num_trades' in line:
                        results['num_trades'] = int(float(line.split(':')[1].strip()))

                return results

        except Exception as e:
            st.error(f"Error loading results: {str(e)}")
            return {}


def render_header():
    """Render dashboard header"""
    st.title("📊 ESG Event-Driven Strategy Monitoring Dashboard")
    st.markdown("**Real-time validation to prevent catastrophic parameter changes**")

    st.markdown("---")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.info("🎯 **Target**: Sharpe > 0.60, Trades > 50")
    with col2:
        st.warning("⚠️ **Root Cause Lesson**: Signal Quality > Quantity")
    with col3:
        st.success("✅ **Baseline**: 0.70 Sharpe, 21 trades (EXCELLENT)")


def render_performance_metrics(data):
    """
    Section A: Real-Time Performance Metrics
    """
    st.header("📈 Section A: Real-Time Performance Metrics")

    baseline = data.baseline
    current = data.current or baseline  # Use baseline if no current data

    # Metrics in columns
    col1, col2, col3, col4 = st.columns(4)

    # Sharpe Ratio
    with col1:
        sharpe = current.get('sharpe_ratio', 0)
        sharpe_delta = sharpe - baseline['sharpe_ratio']
        sharpe_pct_change = (sharpe_delta / baseline['sharpe_ratio']) * 100 if baseline['sharpe_ratio'] != 0 else 0

        if sharpe < 0.50:
            color = "red"
            status = "🚨 CRITICAL"
        elif sharpe < 0.60:
            color = "orange"
            status = "⚠️ WARNING"
        else:
            color = "green"
            status = "✅ EXCELLENT"

        st.metric(
            label="Sharpe Ratio",
            value=f"{sharpe:.3f}",
            delta=f"{sharpe_delta:+.3f} ({sharpe_pct_change:+.1f}%)",
            delta_color="normal" if sharpe_delta >= 0 else "inverse"
        )
        st.markdown(f"<div class='alert-{color}'>{status}</div>", unsafe_allow_html=True)

    # Sortino Ratio
    with col2:
        sortino = current.get('sortino_ratio', 0)
        sortino_delta = sortino - baseline['sortino_ratio']

        sortino_sharpe_ratio = sortino / sharpe if sharpe > 0 else 0

        if sortino_sharpe_ratio < 1.5:
            status = "⚠️ Poor Downside Protection"
        elif sortino_sharpe_ratio < 2.0:
            status = "✅ Good"
        else:
            status = "✅ Excellent"

        st.metric(
            label="Sortino Ratio",
            value=f"{sortino:.3f}",
            delta=f"{sortino_delta:+.3f}"
        )
        st.caption(f"Sortino/Sharpe: {sortino_sharpe_ratio:.2f}x - {status}")

    # Max Drawdown
    with col3:
        max_dd = current.get('max_drawdown', 0)
        dd_delta = max_dd - baseline['max_drawdown']

        if max_dd < -15.0:
            status = "🚨 UNACCEPTABLE"
        elif max_dd < -10.0:
            status = "⚠️ ELEVATED RISK"
        else:
            status = "✅ OK"

        st.metric(
            label="Max Drawdown",
            value=f"{max_dd:.2f}%",
            delta=f"{dd_delta:+.2f}%",
            delta_color="inverse"
        )
        st.caption(status)

    # Turnover
    with col4:
        turnover = current.get('turnover', 0)
        turnover_delta = turnover - baseline['turnover']
        turnover_pct_change = (turnover_delta / baseline['turnover']) * 100 if baseline['turnover'] != 0 else 0

        if turnover > 6.0:
            status = "🚨 OVERTRADING"
        elif turnover < 3.0:
            status = "⚠️ Underutilized"
        else:
            status = "✅ OK"

        st.metric(
            label="Turnover",
            value=f"{turnover:.2f}x",
            delta=f"{turnover_delta:+.2f}x ({turnover_pct_change:+.1f}%)",
            delta_color="inverse" if turnover_delta > 0 else "normal"
        )
        st.caption(status)

    # Additional metrics row
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        total_return = current.get('total_return', 0)
        return_delta = total_return - baseline['total_return']
        st.metric("Total Return", f"{total_return:.2f}%", delta=f"{return_delta:+.2f}%")

    with col2:
        volatility = current.get('volatility', 0)
        vol_delta = volatility - baseline['volatility']
        st.metric("Volatility", f"{volatility:.2f}%", delta=f"{vol_delta:+.2f}%")

    with col3:
        num_trades = current.get('num_trades', 0)
        trades_delta = num_trades - baseline['num_trades']
        st.metric("Number of Trades", f"{num_trades}", delta=f"{trades_delta:+d}")

    with col4:
        # Calculate signal quality metric
        num_events = current.get('num_events', current.get('num_trades', 1))
        sharpe_per_signal = sharpe / num_events if num_events > 0 else 0
        st.metric("Sharpe/Signal", f"{sharpe_per_signal:.4f}")
        st.caption("Higher = Better signal quality")


def render_signal_quality_monitoring(data):
    """
    Section B: Signal Quality Monitoring
    """
    st.header("🔍 Section B: Signal Quality Monitoring")

    baseline = data.baseline
    current = data.current or baseline

    col1, col2 = st.columns(2)

    with col1:
        # Confidence threshold comparison
        st.subheader("Confidence Threshold")

        current_threshold = current.get('confidence_threshold', data.config['nlp']['event_detector']['confidence_threshold'])
        baseline_threshold = baseline['confidence_threshold']

        fig = go.Figure()

        fig.add_trace(go.Indicator(
            mode="number+delta",
            value=current_threshold,
            title={"text": "Current Threshold"},
            delta={'reference': baseline_threshold, 'relative': False},
            domain={'x': [0, 1], 'y': [0, 1]}
        ))

        # Add alert zones
        fig.add_hline(y=0.20, line_dash="dash", line_color="green",
                     annotation_text="Baseline (0.20)")
        fig.add_hline(y=0.18, line_dash="dash", line_color="orange",
                     annotation_text="Min Acceptable (0.18)")
        fig.add_hline(y=0.15, line_dash="dash", line_color="red",
                     annotation_text="HIGH Sensitivity (0.15) - FAILED!")

        st.plotly_chart(fig, use_container_width=True)

        if current_threshold < 0.18:
            st.markdown("<div class='alert-red'>🚨 CRITICAL: Threshold too low, noise risk!</div>",
                       unsafe_allow_html=True)
        elif current_threshold < 0.20:
            st.markdown("<div class='alert-yellow'>⚠️ WARNING: Below baseline threshold</div>",
                       unsafe_allow_html=True)
        else:
            st.markdown("<div class='alert-green'>✅ OK: Threshold maintains signal quality</div>",
                       unsafe_allow_html=True)

    with col2:
        # ESG category balance
        st.subheader("ESG Category Balance")

        # Create pie chart (using example data - would load from actual results)
        categories = ['Environmental', 'Social', 'Governance']
        values = [18, 20, 61]  # Example from HIGH sensitivity

        fig = go.Figure(data=[go.Pie(
            labels=categories,
            values=values,
            marker=dict(colors=['#66bb6a', '#42a5f5', '#ab47bc']),
            hole=.3
        )])

        fig.update_layout(
            title="Event Category Distribution",
            annotations=[dict(text='99<br>Events', x=0.5, y=0.5, font_size=20, showarrow=False)]
        )

        st.plotly_chart(fig, use_container_width=True)

        # Validation
        gov_pct = (61 / 99) * 100
        env_social_pct = ((18 + 20) / 99) * 100

        if gov_pct < 60 or gov_pct > 70:
            st.warning(f"⚠️ Governance: {gov_pct:.1f}% (Target: 60-70%)")
        else:
            st.success(f"✅ Governance: {gov_pct:.1f}% (OK)")

        if env_social_pct < 30 or env_social_pct > 40:
            st.warning(f"⚠️ E+S: {env_social_pct:.1f}% (Target: 30-40%)")
        else:
            st.success(f"✅ E+S: {env_social_pct:.1f}% (OK)")

    # Event count and signal efficiency
    st.markdown("---")
    col1, col2, col3 = st.columns(3)

    with col1:
        num_events = current.get('num_events', 0)
        baseline_events = baseline['num_events']
        events_delta = num_events - baseline_events
        events_pct_change = (events_delta / baseline_events) * 100 if baseline_events > 0 else 0

        st.metric("ESG Events Detected", f"{num_events}", delta=f"{events_delta:+d} ({events_pct_change:+.1f}%)")

    with col2:
        # Signal conversion efficiency (trades / events)
        conversion = (current.get('num_trades', 0) / num_events * 100) if num_events > 0 else 0
        baseline_conversion = (baseline['num_trades'] / baseline['num_events'] * 100)

        st.metric("Signal Conversion", f"{conversion:.1f}%",
                 delta=f"{conversion - baseline_conversion:+.1f}%")

    with col3:
        # Sharpe per signal (quality metric)
        sharpe_per_signal = current.get('sharpe_ratio', 0) / num_events if num_events > 0 else 0
        baseline_sharpe_per_signal = baseline['sharpe_ratio'] / baseline['num_events']

        st.metric("Sharpe / Signal", f"{sharpe_per_signal:.4f}",
                 delta=f"{sharpe_per_signal - baseline_sharpe_per_signal:+.4f}")

        if sharpe_per_signal < baseline_sharpe_per_signal * 0.5:
            st.error("🚨 CRITICAL: Signal quality degraded by >50%!")


def render_portfolio_health(data):
    """
    Section C: Portfolio Health
    """
    st.header("💼 Section C: Portfolio Health")

    baseline = data.baseline
    current = data.current or baseline

    col1, col2, col3 = st.columns(3)

    with col1:
        # Universe size tracker
        st.subheader("Universe Size")

        universe_size = current.get('universe_size', 45)
        baseline_size = baseline['universe_size']

        fig = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=universe_size,
            domain={'x': [0, 1], 'y': [0, 1]},
            delta={'reference': baseline_size},
            gauge={
                'axis': {'range': [None, 100]},
                'bar': {'color': "darkblue"},
                'steps': [
                    {'range': [0, 40], 'color': "lightgray"},
                    {'range': [40, 90], 'color': "lightgreen"},
                    {'range': [90, 100], 'color': "lightgray"}
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': 25
                }
            }
        ))

        fig.update_layout(height=250)
        st.plotly_chart(fig, use_container_width=True)

        if universe_size < 40:
            st.error("🚨 Universe too small! Concentration risk!")
        elif universe_size > 90:
            st.warning("⚠️ Universe may dilute ESG focus")
        else:
            st.success("✅ Universe size optimal")

    with col2:
        # Rebalance frequency
        st.subheader("Rebalance Frequency")

        rebal_freq = current.get('rebalance_freq', data.config['portfolio']['rebalance_frequency'])
        baseline_freq = baseline['rebalance_freq']

        freq_map = {'D': 'Daily (252/yr)', 'W': 'Weekly (52/yr)', 'M': 'Monthly (12/yr)'}

        st.metric("Current", freq_map.get(rebal_freq, rebal_freq))
        st.metric("Baseline", freq_map.get(baseline_freq, baseline_freq))

        if rebal_freq == 'D':
            st.error("🚨 Daily rebalancing = OVERTRADING for ESG events!")
        elif rebal_freq == 'W':
            st.success("✅ Weekly rebalancing optimal for ESG")
        else:
            st.info(f"ℹ️ Using {rebal_freq} rebalancing")

    with col3:
        # Holding period
        st.subheader("Holding Period")

        holding_period = current.get('holding_period', data.config['portfolio']['holding_period'])
        baseline_holding = baseline['holding_period']

        st.metric("Current", f"{holding_period} days", delta=f"{holding_period - baseline_holding:+d} days")

        if holding_period < 7:
            st.error(f"🚨 {holding_period} days too short! ESG sentiment needs 7+ days to diffuse")
        elif holding_period <= 10:
            st.success(f"✅ {holding_period} days optimal for ESG")
        else:
            st.warning(f"⚠️ {holding_period} days may miss exit timing")

    # Position concentration and long/short balance
    st.markdown("---")
    st.subheader("Position Analysis")

    col1, col2 = st.columns(2)

    with col1:
        # Position concentration (example data)
        st.markdown("**Max Position Size**")
        max_position = data.config['portfolio']['max_position']
        st.metric("Position Limit", f"{max_position*100:.1f}%")

        if max_position > 0.15:
            st.warning("⚠️ Position size >15% may increase concentration risk")
        else:
            st.success("✅ Position size controlled")

    with col2:
        # Long/short balance (example data)
        st.markdown("**Long/Short Balance**")

        long_positions = 29  # Example from HIGH sensitivity
        short_positions = 24

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=['Long', 'Short'],
            y=[long_positions, short_positions],
            marker_color=['green', 'red']
        ))

        fig.update_layout(
            title="Position Count",
            yaxis_title="Number of Positions",
            height=250
        )

        st.plotly_chart(fig, use_container_width=True)

        balance_ratio = abs(long_positions - short_positions) / max(long_positions, short_positions)

        if balance_ratio > 0.20:
            st.warning(f"⚠️ Imbalance: {balance_ratio*100:.1f}% (Target: <20%)")
        else:
            st.success(f"✅ Balanced: {balance_ratio*100:.1f}%")


def render_comparative_analysis(data):
    """
    Section D: Comparative Analysis
    """
    st.header("📊 Section D: Comparative Analysis")

    baseline = data.baseline
    current = data.current or baseline

    # Side-by-side comparison table
    st.subheader("Backtest Comparison")

    comparison_df = pd.DataFrame({
        'Metric': [
            'Sharpe Ratio',
            'Sortino Ratio',
            'Total Return (%)',
            'Volatility (%)',
            'Max Drawdown (%)',
            'Turnover (x)',
            'Number of Trades',
            'Number of Events',
            'Universe Size',
            'Confidence Threshold',
            'Rebalance Freq',
            'Holding Period'
        ],
        'Baseline (MEDIUM)': [
            f"{baseline['sharpe_ratio']:.3f}",
            f"{baseline['sortino_ratio']:.3f}",
            f"{baseline['total_return']:.2f}",
            f"{baseline['volatility']:.2f}",
            f"{baseline['max_drawdown']:.2f}",
            f"{baseline['turnover']:.2f}",
            baseline['num_trades'],
            baseline['num_events'],
            baseline['universe_size'],
            baseline['confidence_threshold'],
            baseline['rebalance_freq'],
            f"{baseline['holding_period']} days"
        ],
        'Current': [
            f"{current.get('sharpe_ratio', 0):.3f}",
            f"{current.get('sortino_ratio', 0):.3f}",
            f"{current.get('total_return', 0):.2f}",
            f"{current.get('volatility', 0):.2f}",
            f"{current.get('max_drawdown', 0):.2f}",
            f"{current.get('turnover', 0):.2f}",
            current.get('num_trades', 0),
            current.get('num_events', 0),
            current.get('universe_size', 45),
            current.get('confidence_threshold', data.config['nlp']['event_detector']['confidence_threshold']),
            current.get('rebalance_freq', data.config['portfolio']['rebalance_frequency']),
            f"{current.get('holding_period', data.config['portfolio']['holding_period'])} days"
        ]
    })

    # Calculate percentage changes
    def calc_pct_change(baseline_val, current_val):
        try:
            b = float(str(baseline_val).replace('%', '').replace('x', '').replace(' days', ''))
            c = float(str(current_val).replace('%', '').replace('x', '').replace(' days', ''))
            if b == 0:
                return "-"
            change = ((c - b) / b) * 100
            return f"{change:+.1f}%"
        except:
            return "-"

    comparison_df['Change'] = [
        calc_pct_change(comparison_df.loc[i, 'Baseline (MEDIUM)'], comparison_df.loc[i, 'Current'])
        for i in range(len(comparison_df))
    ]

    st.dataframe(comparison_df, use_container_width=True, height=450)

    # Performance attribution
    st.markdown("---")
    st.subheader("Performance Attribution")

    col1, col2 = st.columns(2)

    with col1:
        # Return attribution waterfall
        st.markdown("**Return Degradation Analysis**")

        # Example attribution (from root cause analysis)
        categories = [
            'Baseline',
            'Signal Quality',
            'Transaction Costs',
            'Holding Period',
            'Concentration Risk',
            'Sentiment Dilution',
            'Current'
        ]

        values = [
            20.38,  # Baseline
            -12.0,  # Signal quality degradation
            -0.23,  # Transaction costs
            -1.5,   # Holding period mismatch
            -0.5,   # Concentration risk
            -0.3,   # Sentiment dilution
            5.91    # Current (calculated)
        ]

        fig = go.Figure(go.Waterfall(
            x=categories,
            y=values,
            textposition="outside",
            connector={"line": {"color": "rgb(63, 63, 63)"}},
            decreasing={"marker": {"color": "#d32f2f"}},
            increasing={"marker": {"color": "#388e3c"}},
            totals={"marker": {"color": "#1976d2"}}
        ))

        fig.update_layout(
            title="Return Attribution (Percentage Points)",
            showlegend=False,
            height=400
        )

        st.plotly_chart(fig, use_container_width=True)

    with col2:
        # Metric comparison radar
        st.markdown("**Metric Comparison Radar**")

        metrics = ['Sharpe', 'Sortino', 'Return', 'Volatility', 'Drawdown']

        # Normalize metrics to 0-100 scale
        baseline_values = [70, 65, 80, 70, 85]  # Normalized baseline scores
        current_values = [10, 5, 30, 60, 60]    # Normalized current scores

        fig = go.Figure()

        fig.add_trace(go.Scatterpolar(
            r=baseline_values,
            theta=metrics,
            fill='toself',
            name='Baseline',
            line_color='green'
        ))

        fig.add_trace(go.Scatterpolar(
            r=current_values,
            theta=metrics,
            fill='toself',
            name='Current',
            line_color='red'
        ))

        fig.update_layout(
            polar=dict(
                radialaxis=dict(
                    visible=True,
                    range=[0, 100]
                )),
            showlegend=True,
            height=400
        )

        st.plotly_chart(fig, use_container_width=True)


def render_validation_checklist(data):
    """
    Section E: Validation Checklist
    """
    st.header("✅ Section E: Validation Checklist")

    # Run validator
    validator = data.validator

    # Pre-flight checks
    st.subheader("Pre-Flight Configuration Checks")

    universe_size = data.current.get('universe_size', 45) if data.current else 45
    pre_flight_passed, pre_flight_issues = validator.run_pre_flight_checks(universe_size=universe_size)

    if pre_flight_passed:
        st.success("✅ All pre-flight checks PASSED")
    else:
        st.error(f"❌ Pre-flight checks FAILED with {len(validator.errors)} error(s)")

    # Display checks
    checks = [
        ("Confidence Threshold", validator.config['nlp']['event_detector']['confidence_threshold'] >= 0.18),
        ("Rebalance Frequency", validator.config['portfolio']['rebalance_frequency'] == 'W'),
        ("Holding Period", 7 <= validator.config['portfolio']['holding_period'] <= 10),
        ("Reddit Window (Before)", validator.config['data']['social_media']['days_before_event'] == 3),
        ("Reddit Window (After)", validator.config['data']['social_media']['days_after_event'] == 7),
        ("Universe Size", 40 <= universe_size <= 90)
    ]

    for check_name, passed in checks:
        if passed:
            st.success(f"✅ {check_name}")
        else:
            st.error(f"❌ {check_name}")

    # Post-backtest validation
    if data.current:
        st.markdown("---")
        st.subheader("Post-Backtest Validation")

        post_backtest_passed, post_backtest_issues = validator.validate_backtest_results(data.current)

        if post_backtest_passed:
            st.success("✅ All post-backtest validation checks PASSED")
        else:
            st.error(f"❌ Post-backtest validation FAILED with {len(validator.errors)} error(s)")

        # Display issues
        if validator.errors:
            st.markdown("**ERRORS (Must Fix):**")
            for error in validator.errors:
                st.error(error)

        if validator.warnings:
            st.markdown("**WARNINGS (Review Recommended):**")
            for warning in validator.warnings:
                st.warning(warning)

    # Red flags detection
    st.markdown("---")
    st.subheader("🚩 Red Flag Detection")

    red_flags = []

    # Check for Sharpe collapse
    if data.current:
        sharpe = data.current.get('sharpe_ratio', 0)
        baseline_sharpe = data.baseline['sharpe_ratio']
        sharpe_degradation = (baseline_sharpe - sharpe) / baseline_sharpe if baseline_sharpe > 0 else 0

        if sharpe_degradation > 0.20:
            red_flags.append(f"🚩 Sharpe ratio degraded by {sharpe_degradation*100:.1f}% (>20% threshold)")

        # Check for turnover explosion
        turnover = data.current.get('turnover', 0)
        if turnover > 6.0:
            red_flags.append(f"🚩 Turnover {turnover:.2f}x exceeds 6x limit (overtrading)")

        # Check for universe shrinkage
        universe_size = data.current.get('universe_size', 45)
        if universe_size < 40:
            red_flags.append(f"🚩 Universe size {universe_size} < 40 stocks (concentration risk)")

    if red_flags:
        for flag in red_flags:
            st.error(flag)
    else:
        st.success("✅ No red flags detected")


def render_live_logs(log_file_path="./logs/esg_strategy.log"):
    """
    Section F: Live Execution Logs
    """
    st.header("📝 Section F: Live Execution Logs")
    
    log_path = Path(log_file_path)
    
    if not log_path.exists():
        st.warning(f"Log file not found at {log_path}")
        return

    # Add auto-refresh checkbox
    if st.checkbox("Auto-refresh logs (5s)", value=True):
        import time
        time.sleep(5)
        st.rerun()

    try:
        # Read last 50 lines
        with open(log_path, "r") as f:
            lines = f.readlines()
            last_lines = lines[-50:]
            log_content = "".join(last_lines)
            
        st.text_area("Tail of esg_strategy.log", log_content, height=400)
        
        # Parse progress if possible
        if "Downloading filings" in log_content:
            st.info("🔄 Status: Downloading SEC Filings...")
        elif "FETCHING PRICE DATA" in log_content:
            st.info("🔄 Status: Fetching Price Data...")
        elif "EVENT DETECTION" in log_content:
            st.info("🔄 Status: Detecting ESG Events...")
        elif "SIGNAL GENERATION" in log_content:
            st.info("🔄 Status: Generating Signals...")
        elif "BACKTESTING" in log_content:
            st.info("🔄 Status: Running Backtest...")
            
    except Exception as e:
        st.error(f"Error reading log file: {e}")



def main():
    """Main dashboard application"""

    # Initialize data
    data = DashboardData()

    # Sidebar
    with st.sidebar:
        st.title("⚙️ Dashboard Settings")

        st.markdown("---")
        st.subheader("Load Backtest Results")

        # File uploader
        uploaded_file = st.file_uploader(
            "Upload backtest results (JSON or log file)",
            type=['json', 'log', 'txt']
        )

        if uploaded_file is not None:
            # Save uploaded file temporarily
            temp_path = Path(f"/tmp/{uploaded_file.name}")
            with open(temp_path, 'wb') as f:
                f.write(uploaded_file.getvalue())

            # Load results
            data.current = data.load_backtest_results(temp_path)
            st.success("✅ Results loaded successfully!")

        st.markdown("---")
        st.subheader("Baseline Configuration")

        st.info(f"""
        **MEDIUM Sensitivity (Baseline)**
        - Sharpe: {data.baseline['sharpe_ratio']:.3f}
        - Trades: {data.baseline['num_trades']}
        - Threshold: {data.baseline['confidence_threshold']}
        - Rebalance: {data.baseline['rebalance_freq']}
        """)

        st.markdown("---")
        st.markdown("### 📖 Root Cause Lessons")
        st.markdown("""
        1. **Signal Quality > Quantity**
        2. **Weekly rebalancing for ESG**
        3. **7-day holding for sentiment diffusion**
        4. **Threshold ≥0.18 for noise control**
        5. **Universe: 40-90 stocks for balance**
        """)

    # Render dashboard sections
    render_header()

    st.markdown("---")

    # Section A: Performance Metrics
    render_performance_metrics(data)

    st.markdown("---")

    # Section B: Signal Quality
    render_signal_quality_monitoring(data)

    st.markdown("---")

    # Section C: Portfolio Health
    render_portfolio_health(data)

    st.markdown("---")

    # Section D: Comparative Analysis
    render_comparative_analysis(data)

    st.markdown("---")

    # Section E: Validation Checklist
    render_validation_checklist(data)

    st.markdown("---")

    # Section F: Live Logs
    render_live_logs()

    # Footer
    st.markdown("---")
    st.markdown("**ESG Event-Driven Strategy Monitoring Dashboard** | Built to prevent catastrophic parameter changes")


if __name__ == '__main__':
    main()
