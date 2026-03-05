"""
Comprehensive Backtest Comparison: MEDIUM vs HIGH Sensitivity
Generates side-by-side visualizations comparing the two strategies
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from datetime import datetime

# Set style
plt.style.use('seaborn-v0_8-darkgrid')
fig = plt.figure(figsize=(20, 12))
fig.suptitle('ESG Event-Driven Alpha Strategy: MEDIUM vs HIGH Sensitivity Comparison\n2024-01-01 to 2025-10-01 (22 months)',
             fontsize=18, fontweight='bold', y=0.98)

# Data from both backtests
original = {
    'name': 'ORIGINAL (MEDIUM)',
    'universe_size': 45,
    'total_return': 20.38,
    'sharpe': 0.70,
    'sortino': 1.29,
    'max_dd': -5.29,
    'volatility': 7.08,
    'num_trades': 21,
    'turnover': 3.19,
    'esg_events': 58,
    'e_events': 0,
    's_events': 2,
    'g_events': 56,
    'reddit_coverage': 65.5,
    'sentiment_corr': 0.786,
    'cagr': 6.92,
    'rebalance': 'Weekly',
    'threshold': 0.20,
    'holding_period': 7,
    'final_value': 1203803
}

improved = {
    'name': 'IMPROVED (HIGH)',
    'universe_size': 25,
    'total_return': 5.91,
    'sharpe': 0.04,
    'sortino': 0.06,
    'max_dd': -7.88,
    'volatility': 6.33,
    'num_trades': 50,
    'turnover': 7.44,
    'esg_events': 99,  # Total events detected (77 with Reddit)
    'e_events': 18,
    's_events': 20,
    'g_events': 61,
    'reddit_coverage': 77.8,
    'sentiment_corr': 0.760,
    'cagr': 2.09,
    'rebalance': 'Daily',
    'threshold': 0.15,
    'holding_period': 5,
    'final_value': 1059056
}

# 1. Performance Metrics Comparison (Top Left)
ax1 = plt.subplot(3, 3, 1)
metrics = ['Total Return\n(%)', 'Sharpe\nRatio', 'CAGR\n(%)']
orig_vals = [original['total_return'], original['sharpe'], original['cagr']]
imp_vals = [improved['total_return'], improved['sharpe'], improved['cagr']]

x = np.arange(len(metrics))
width = 0.35

bars1 = ax1.bar(x - width/2, orig_vals, width, label='ORIGINAL', color='#2ecc71', alpha=0.8)
bars2 = ax1.bar(x + width/2, imp_vals, width, label='IMPROVED', color='#e74c3c', alpha=0.8)

ax1.set_ylabel('Value', fontweight='bold')
ax1.set_title('Performance Metrics', fontweight='bold', fontsize=12)
ax1.set_xticks(x)
ax1.set_xticklabels(metrics, fontsize=9)
ax1.legend()
ax1.grid(axis='y', alpha=0.3)

# Add value labels on bars
for bars in [bars1, bars2]:
    for bar in bars:
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.2f}', ha='center', va='bottom', fontsize=8)

# 2. Risk Metrics Comparison (Top Center)
ax2 = plt.subplot(3, 3, 2)
risk_metrics = ['Max DD\n(%)', 'Volatility\n(%)', 'Sortino\nRatio']
orig_risk = [abs(original['max_dd']), original['volatility'], original['sortino']]
imp_risk = [abs(improved['max_dd']), improved['volatility'], improved['sortino']]

x = np.arange(len(risk_metrics))
bars1 = ax2.bar(x - width/2, orig_risk, width, label='ORIGINAL', color='#3498db', alpha=0.8)
bars2 = ax2.bar(x + width/2, imp_risk, width, label='IMPROVED', color='#f39c12', alpha=0.8)

ax2.set_ylabel('Value', fontweight='bold')
ax2.set_title('Risk Metrics', fontweight='bold', fontsize=12)
ax2.set_xticks(x)
ax2.set_xticklabels(risk_metrics, fontsize=9)
ax2.legend()
ax2.grid(axis='y', alpha=0.3)

for bars in [bars1, bars2]:
    for bar in bars:
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.2f}', ha='center', va='bottom', fontsize=8)

# 3. Trading Activity (Top Right)
ax3 = plt.subplot(3, 3, 3)
trading_metrics = ['# Trades', 'Turnover\n(x)']
orig_trading = [original['num_trades'], original['turnover']]
imp_trading = [improved['num_trades'], improved['turnover']]

x = np.arange(len(trading_metrics))
bars1 = ax3.bar(x - width/2, orig_trading, width, label='ORIGINAL', color='#9b59b6', alpha=0.8)
bars2 = ax3.bar(x + width/2, imp_trading, width, label='IMPROVED', color='#1abc9c', alpha=0.8)

ax3.set_ylabel('Value', fontweight='bold')
ax3.set_title('Trading Activity', fontweight='bold', fontsize=12)
ax3.set_xticks(x)
ax3.set_xticklabels(trading_metrics, fontsize=9)
ax3.legend()
ax3.grid(axis='y', alpha=0.3)

# Add target line for trades
ax3.axhline(y=50, color='red', linestyle='--', linewidth=2, label='Target (>50)', alpha=0.7)
ax3.legend()

for bars in [bars1, bars2]:
    for bar in bars:
        height = bar.get_height()
        ax3.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.1f}', ha='center', va='bottom', fontsize=8)

# 4. ESG Event Distribution Pie Charts (Middle Left & Center)
ax4 = plt.subplot(3, 3, 4)
orig_esg = [original['e_events'], original['s_events'], original['g_events']]
colors_esg = ['#27ae60', '#3498db', '#e67e22']
labels_esg = ['Environmental', 'Social', 'Governance']

wedges, texts, autotexts = ax4.pie(orig_esg, labels=labels_esg, autopct='%1.1f%%',
                                     colors=colors_esg, startangle=90)
ax4.set_title(f'ORIGINAL ESG Distribution\n({original["esg_events"]} total events)',
              fontweight='bold', fontsize=11)

ax5 = plt.subplot(3, 3, 5)
imp_esg = [improved['e_events'], improved['s_events'], improved['g_events']]

wedges, texts, autotexts = ax5.pie(imp_esg, labels=labels_esg, autopct='%1.1f%%',
                                     colors=colors_esg, startangle=90)
ax5.set_title(f'IMPROVED ESG Distribution\n({improved["esg_events"]} total events)',
              fontweight='bold', fontsize=11)

# 5. ESG Category Comparison (Middle Right)
ax6 = plt.subplot(3, 3, 6)
categories = ['E', 'S', 'G']
orig_cat = [original['e_events'], original['s_events'], original['g_events']]
imp_cat = [improved['e_events'], improved['s_events'], improved['g_events']]

x = np.arange(len(categories))
width = 0.35

bars1 = ax6.bar(x - width/2, orig_cat, width, label='ORIGINAL', color='#2ecc71', alpha=0.8)
bars2 = ax6.bar(x + width/2, imp_cat, width, label='IMPROVED', color='#e74c3c', alpha=0.8)

ax6.set_ylabel('Number of Events', fontweight='bold')
ax6.set_title('ESG Event Count by Category', fontweight='bold', fontsize=12)
ax6.set_xticks(x)
ax6.set_xticklabels(categories)
ax6.legend()
ax6.grid(axis='y', alpha=0.3)

for bars in [bars1, bars2]:
    for bar in bars:
        height = bar.get_height()
        if height > 0:
            ax6.text(bar.get_x() + bar.get_width()/2., height,
                    f'{int(height)}', ha='center', va='bottom', fontsize=9)

# 6. Configuration Comparison Table (Bottom Left)
ax7 = plt.subplot(3, 3, 7)
ax7.axis('off')

config_data = [
    ['Configuration', 'ORIGINAL', 'IMPROVED'],
    ['Universe Size', f"{original['universe_size']} stocks", f"{improved['universe_size']} stocks"],
    ['Rebalance Freq', original['rebalance'], improved['rebalance']],
    ['Holding Period', f"{original['holding_period']} days", f"{improved['holding_period']} days"],
    ['Confidence Threshold', f"{original['threshold']:.2f}", f"{improved['threshold']:.2f}"],
    ['Reddit Coverage', f"{original['reddit_coverage']:.1f}%", f"{improved['reddit_coverage']:.1f}%"],
    ['Sentiment Corr', f"{original['sentiment_corr']:.3f}", f"{improved['sentiment_corr']:.3f}"],
]

table = ax7.table(cellText=config_data, cellLoc='center', loc='center',
                  colWidths=[0.35, 0.32, 0.32])
table.auto_set_font_size(False)
table.set_fontsize(9)
table.scale(1, 2.5)

# Style header row
for i in range(3):
    table[(0, i)].set_facecolor('#34495e')
    table[(0, i)].set_text_props(weight='bold', color='white')

# Color code rows
for i in range(1, len(config_data)):
    table[(i, 0)].set_facecolor('#ecf0f1')
    table[(i, 1)].set_facecolor('#d5f4e6')  # Green tint for original
    table[(i, 2)].set_facecolor('#fadbd8')  # Red tint for improved

ax7.set_title('Strategy Configuration', fontweight='bold', fontsize=12, pad=20)

# 7. Performance Summary Table (Bottom Center)
ax8 = plt.subplot(3, 3, 8)
ax8.axis('off')

summary_data = [
    ['Metric', 'ORIGINAL', 'IMPROVED', 'Change'],
    ['Total Return', f"{original['total_return']:.2f}%", f"{improved['total_return']:.2f}%",
     f"{((improved['total_return']/original['total_return']-1)*100):.1f}%"],
    ['Sharpe Ratio', f"{original['sharpe']:.2f}", f"{improved['sharpe']:.2f}",
     f"{((improved['sharpe']/original['sharpe']-1)*100):.1f}%"],
    ['Max Drawdown', f"{original['max_dd']:.2f}%", f"{improved['max_dd']:.2f}%",
     f"{((abs(improved['max_dd'])/abs(original['max_dd'])-1)*100):.1f}%"],
    ['# Trades', f"{original['num_trades']}", f"{improved['num_trades']}",
     f"+{improved['num_trades']-original['num_trades']}"],
    ['ESG Events', f"{original['esg_events']}", f"{improved['esg_events']}",
     f"+{improved['esg_events']-original['esg_events']}"],
    ['Final Value', f"${original['final_value']:,}", f"${improved['final_value']:,}",
     f"${improved['final_value']-original['final_value']:,}"],
]

table2 = ax8.table(cellText=summary_data, cellLoc='center', loc='center',
                   colWidths=[0.28, 0.24, 0.24, 0.24])
table2.auto_set_font_size(False)
table2.set_fontsize(8)
table2.scale(1, 2.2)

# Style header row
for i in range(4):
    table2[(0, i)].set_facecolor('#34495e')
    table2[(0, i)].set_text_props(weight='bold', color='white')

# Color code based on improvement/degradation
for i in range(1, len(summary_data)):
    table2[(i, 0)].set_facecolor('#ecf0f1')
    table2[(i, 1)].set_facecolor('#d5f4e6')
    table2[(i, 2)].set_facecolor('#fadbd8')

    # Color change column based on direction
    change_val = summary_data[i][3]
    if '-' in change_val or (i == 3):  # Max DD worse = negative
        table2[(i, 3)].set_facecolor('#fadbd8')  # Red for worse
    else:
        table2[(i, 3)].set_facecolor('#d5f4e6')  # Green for better

ax8.set_title('Performance Summary', fontweight='bold', fontsize=12, pad=20)

# 8. Key Findings & Recommendations (Bottom Right)
ax9 = plt.subplot(3, 3, 9)
ax9.axis('off')

findings_text = """
KEY FINDINGS

✅ SUCCESSES (IMPROVED):
• Achieved >50 trades target (50 vs 21)
• Environmental events: 0 → 18 (∞%)
• Social events: 2 → 20 (+900%)
• Total ESG events: +71%
• Reddit coverage: +19% (77.8%)

❌ CRITICAL ISSUES (IMPROVED):
• Sharpe ratio collapsed: -94%
• Total return dropped: -71%
• Max drawdown worse: +49%
• Turnover doubled: +133%

RECOMMENDATION:
The ORIGINAL strategy (MEDIUM) is
superior despite lower trade count:
• 17.5x better Sharpe ratio
• 3.5x higher returns
• Better risk management

Trade-off: Quality over Quantity
21 high-quality trades > 50 weak trades
"""

ax9.text(0.05, 0.95, findings_text, transform=ax9.transAxes,
         fontsize=9, verticalalignment='top', fontfamily='monospace',
         bbox=dict(boxstyle='round', facecolor='#f8f9fa', alpha=0.8,
                  edgecolor='#34495e', linewidth=2))

# Add timestamp
timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
fig.text(0.99, 0.01, f'Generated: {timestamp}', ha='right', fontsize=8,
         style='italic', color='gray')

plt.tight_layout(rect=[0, 0.02, 1, 0.96])
plt.savefig('results/visualizations/COMPARISON_MEDIUM_vs_HIGH.png',
            dpi=300, bbox_inches='tight')
print(f"✓ Comparison visualization saved: results/visualizations/COMPARISON_MEDIUM_vs_HIGH.png")

plt.show()
