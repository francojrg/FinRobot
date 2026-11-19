import os
import mplfinance as mpf
import pandas as pd

from matplotlib import pyplot as plt
from typing import Annotated, List, Tuple
from pandas import DateOffset
from datetime import datetime, timedelta

from ..data_source.yfinance_utils import YFinanceUtils


class MplFinanceUtils:

    def plot_stock_price_chart(
        ticker_symbol: Annotated[
            str, "Ticker symbol of the stock (e.g., 'AAPL' for Apple)"
        ],
        start_date: Annotated[
            str, "Start date of the historical data in 'YYYY-MM-DD' format"
        ],
        end_date: Annotated[
            str, "End date of the historical data in 'YYYY-MM-DD' format"
        ],
        save_path: Annotated[str, "File path where the plot should be saved"],
        verbose: Annotated[
            str, "Whether to print stock data to console. Default to False."
        ] = False,
        type: Annotated[
            str,
            "Type of the plot, should be one of 'candle','ohlc','line','renko','pnf','hollow_and_filled'. Default to 'candle'",
        ] = "candle",
        style: Annotated[
            str,
            "Style of the plot, should be one of 'default','classic','charles','yahoo','nightclouds','sas','blueskies','mike'. Default to 'default'.",
        ] = "default",
        mav: Annotated[
            int | List[int] | Tuple[int, ...] | None,
            "Moving average window(s) to plot on the chart. Default to None.",
        ] = None,
        show_nontrading: Annotated[
            bool, "Whether to show non-trading days on the chart. Default to False."
        ] = False,
    ) -> str:
        """
        Plot a stock price chart using mplfinance for the specified stock and time period,
        and save the plot to a file.
        """
        # Fetch historical data
        stock_data = YFinanceUtils.get_stock_data(ticker_symbol, start_date, end_date)
        if verbose:
            print(stock_data.to_string())

        params = {
            "type": type,
            "style": style,
            "title": f"{ticker_symbol} {type} chart",
            "ylabel": "Price",
            "volume": True,
            "ylabel_lower": "Volume",
            "mav": mav,
            "show_nontrading": show_nontrading,
            "savefig": save_path,
        }
        # Using dictionary comprehension to filter out None values (MplFinance does not accept None values)
        filtered_params = {k: v for k, v in params.items() if v is not None}

        # Plot chart
        mpf.plot(stock_data, **filtered_params)

        return f"{type} chart saved to <img {save_path}>"


class ReportChartUtils:

    # Angepasst: Kursentwicklung ueber mehrere Jahre (Standard 3) statt nur 1 Jahr, im Stil des
    # Bewertungs-Charts. Das Original bleibt als _get_share_performance_original erhalten.
    def get_share_performance(
        ticker_symbol: Annotated[
            str, "Ticker symbol of the stock (e.g., 'AAPL' for Apple)"
        ],
        filing_date: Annotated[str | datetime, "filing date in 'YYYY-MM-DD' format"],
        save_path: Annotated[str, "File path where the plot should be saved"],
        years: Annotated[int, "number of years to show, default 3"] = 3,
    ) -> str:
        """Plot the share price performance of a company compared to the S&P 500 over the past years (default 3), rebased to 100."""
        if isinstance(filing_date, str):
            filing_date = datetime.strptime(filing_date, "%Y-%m-%d")
        start = (filing_date - timedelta(days=round(365.25 * years))).strftime("%Y-%m-%d")
        end = (filing_date + timedelta(days=1)).strftime("%Y-%m-%d")

        def closes(sym):
            s = YFinanceUtils.get_stock_data(sym, start, end)["Close"].dropna()
            s.index = s.index.tz_localize(None) if getattr(s.index, "tz", None) is not None else s.index
            return s

        stock, index = closes(ticker_symbol), closes("^GSPC")
        if stock.empty:
            raise ValueError(f"Keine Kursdaten fuer {ticker_symbol} im Zeitraum {start} bis {end}.")
        index = index[index.index >= stock.index[0]]
        reb_s = stock / stock.iloc[0] * 100
        reb_i = index / index.iloc[0] * 100 if not index.empty else index
        name = (YFinanceUtils.get_stock_info(ticker_symbol) or {}).get("shortName", ticker_symbol)
        span = f"{stock.index[0]:%b %Y} - {stock.index[-1]:%b %Y}"

        plt.rcParams.update({"font.size": 11})
        fig, ax = plt.subplots(figsize=(9, 4.6))
        ax.plot(reb_s.index, reb_s.values, color="#1f4e79", lw=1.5,
                label=f"{name}: {reb_s.iloc[-1] - 100:+.0f}%")
        if not reb_i.empty:
            ax.plot(reb_i.index, reb_i.values, color="#c0504d", lw=1.2,
                    label=f"S&P 500: {reb_i.iloc[-1] - 100:+.0f}%")
        ax.axhline(100, color="#999999", lw=0.8, ls=":")
        ax.set_title(f"{name} vs S&P 500, rebased to 100 ({span})", fontsize=12)
        ax.set_ylabel("Indexed (start = 100)")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=9, loc="upper left")
        plt.tight_layout()
        plot_path = f"{save_path}/stock_performance.png" if os.path.isdir(save_path) else save_path
        plt.savefig(plot_path, dpi=150)
        plt.close()
        return f"{years}-year stock performance chart saved to <img {plot_path}>"

    def _get_share_performance_original(
        ticker_symbol: Annotated[
            str, "Ticker symbol of the stock (e.g., 'AAPL' for Apple)"
        ],
        filing_date: Annotated[str | datetime, "filing date in 'YYYY-MM-DD' format"],
        save_path: Annotated[str, "File path where the plot should be saved"],
    ) -> str:
        """Plot the stock performance of a company compared to the S&P 500 over the past year."""
        if isinstance(filing_date, str):
            filing_date = datetime.strptime(filing_date, "%Y-%m-%d")

        def fetch_stock_data(ticker):
            start = (filing_date - timedelta(days=365)).strftime("%Y-%m-%d")
            end = filing_date.strftime("%Y-%m-%d")
            historical_data = YFinanceUtils.get_stock_data(ticker, start, end)
            # hist = stock.history(period=period)
            return historical_data["Close"]

        target_close = fetch_stock_data(ticker_symbol)
        sp500_close = fetch_stock_data("^GSPC")
        info = YFinanceUtils.get_stock_info(ticker_symbol)

        # 计算变化率
        company_change = (
            (target_close - target_close.iloc[0]) / target_close.iloc[0] * 100
        )
        sp500_change = (sp500_close - sp500_close.iloc[0]) / sp500_close.iloc[0] * 100

        # 计算额外的日期点
        start_date = company_change.index.min()
        four_months = start_date + DateOffset(months=4)
        eight_months = start_date + DateOffset(months=8)
        end_date = company_change.index.max()

        # 准备绘图
        plt.rcParams.update({"font.size": 20})  # 调整为更大的字体大小
        plt.figure(figsize=(14, 7))
        plt.plot(
            company_change.index,
            company_change,
            label=f'{info["shortName"]} Change %',
            color="blue",
        )
        plt.plot(
            sp500_change.index, sp500_change, label="S&P 500 Change %", color="red"
        )

        # 设置标题和标签
        plt.title(f'{info["shortName"]} vs S&P 500 - Change % Over the Past Year')
        plt.xlabel("Date")
        plt.ylabel("Change %")

        # 设置x轴刻度标签
        plt.xticks(
            [start_date, four_months, eight_months, end_date],
            [
                start_date.strftime("%Y-%m"),
                four_months.strftime("%Y-%m"),
                eight_months.strftime("%Y-%m"),
                end_date.strftime("%Y-%m"),
            ],
        )

        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        # plt.show()
        plot_path = (
            f"{save_path}/stock_performance.png"
            if os.path.isdir(save_path)
            else save_path
        )
        plt.savefig(plot_path)
        plt.close()
        return f"last year stock performance chart saved to <img {plot_path}>"

    # Angepasst: Das Original (KGV/EPS-Linien aus 4 Jahrespunkten) ist bei Verlustunternehmen
    # oekonomisch sinnlos (negative KGVs). Neue Version unter gleichem Namen, damit Agent und
    # Report-Funktion unveraendert weiterarbeiten. Das Original bleibt als
    # _get_pe_eps_performance_original erhalten (Unterstrich = wird nicht als Tool registriert).
    def get_pe_eps_performance(
        ticker_symbol: Annotated[
            str, "Ticker symbol of the stock (e.g., 'AAPL' for Apple)"
        ],
        filing_date: Annotated[str | datetime, "filing date in 'YYYY-MM-DD' format"],
        years: Annotated[int, "number of years to search from, default to 4"] = 4,
        save_path: Annotated[str, "File path where the plot should be saved"] = None,
    ) -> str:
        """Plot the valuation chart: historical P/E band (or EV/Sales band if the company is loss-making) with mean and +/-1 standard deviation, plus FCF yield per fiscal year."""
        import numpy as np
        import yfinance as yf

        if isinstance(filing_date, str):
            filing_date = datetime.strptime(filing_date, "%Y-%m-%d")
        t = yf.Ticker(ticker_symbol)
        inc, bs, cf = t.income_stmt, t.balance_sheet, t.cashflow
        if inc is None or inc.empty:
            raise ValueError(f"Keine Jahresabschluesse fuer {ticker_symbol} bei Yahoo Finance.")

        def val(df, rows, col):
            for r in rows:
                if df is not None and r in df.index and col in df.columns and pd.notna(df.at[r, col]):
                    return float(df.at[r, col])
            return None

        fy = sorted([c for c in inc.columns if val(inc, ["Total Revenue"], c) is not None
                     and pd.Timestamp(c) <= pd.Timestamp(filing_date)])[-years:]
        if not fy:
            raise ValueError("Keine Geschaeftsjahre vor dem Einreichungsdatum verfuegbar.")
        fund = []
        for c in fy:
            fcf = val(cf, ["Free Cash Flow"], c)
            if fcf is None:
                ocf, capex = val(cf, ["Operating Cash Flow"], c), val(cf, ["Capital Expenditure"], c)
                fcf = None if ocf is None or capex is None else ocf + capex
            fund.append({
                "date": pd.Timestamp(c), "rev": val(inc, ["Total Revenue"], c),
                "eps": val(inc, ["Diluted EPS", "Basic EPS"], c),
                "shares": val(bs, ["Ordinary Shares Number", "Share Issued"], c)
                          or val(inc, ["Diluted Average Shares", "Basic Average Shares"], c),
                "debt": val(bs, ["Total Debt"], c) or 0.0,
                "cash": val(bs, ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"], c) or 0.0,
                "fcf": fcf,
            })
        fund = pd.DataFrame(fund).set_index("date").sort_index()

        hist = t.history(start=(fund.index[0] - timedelta(days=10)).strftime("%Y-%m-%d"),
                         end=(filing_date + timedelta(days=1)).strftime("%Y-%m-%d"), auto_adjust=False)
        if hist.empty:
            raise ValueError("Keine Kursdaten verfuegbar.")
        px = hist["Close"].copy()
        px.index = px.index.tz_localize(None) if px.index.tz is not None else px.index
        # Fuer jeden Handelstag die zuletzt veroeffentlichten Jahreszahlen (vereinfachend: ab Stichtag)
        f_daily = fund.reindex(px.index, method="ffill")
        profitable = bool((fund["eps"].dropna() > 0).all()) and fund["eps"].notna().all()
        if profitable:
            series = px / f_daily["eps"]
            label = "P/E (trailing, annual EPS)"
        else:
            ev = px * f_daily["shares"] + f_daily["debt"] - f_daily["cash"]
            series = ev / f_daily["rev"]
            label = "EV/Sales (trailing, annual revenue)"
        series = series.replace([np.inf, -np.inf], np.nan).dropna()
        series = series[series.index >= fund.index[0]]
        mu, sd = series.mean(), series.std()

        # FCF-Rendite je Geschaeftsjahr (FCF / Marktkapitalisierung zum Stichtag)
        fcf_y = []
        for d, r in fund.iterrows():
            p = px[px.index <= d]
            mcap = None if p.empty or not r["shares"] else float(p.iloc[-1]) * r["shares"]
            fcf_y.append(None if mcap is None or r["fcf"] is None else r["fcf"] / mcap * 100)

        name = (YFinanceUtils.get_stock_info(ticker_symbol) or {}).get("shortName", ticker_symbol)
        plt.rcParams.update({"font.size": 11})
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 5.6), gridspec_kw={"height_ratios": [2.2, 1]})
        ax1.plot(series.index, series.values, color="#1f4e79", lw=1.4, label=f"{label}, current {series.iloc[-1]:.1f}x")
        ax1.axhline(mu, color="#444444", ls="--", lw=1, label=f"Mean {mu:.1f}x")
        ax1.axhline(mu + sd, color="#999999", ls=":", lw=1, label=f"\u00b11 SD ({mu - sd:.1f}x \u2013 {mu + sd:.1f}x)")
        ax1.axhline(mu - sd, color="#999999", ls=":", lw=1)
        ax1.fill_between(series.index, mu - sd, mu + sd, color="#1f4e79", alpha=0.07)
        ax1.plot(series.index[-1], series.iloc[-1], "o", color="#1f4e79", ms=4)
        ax1.set_title(f"{name}: {label.split(' (')[0]} with historical mean and \u00b11 SD", fontsize=12)
        ax1.set_ylabel(label.split(" (")[0])
        ax1.grid(alpha=0.3)
        ax1.legend(fontsize=9, loc="upper left")

        labels = [d.strftime("FY%Y") for d in fund.index]
        vals = [v if v is not None else 0 for v in fcf_y]
        bars = ax2.bar(labels, vals, color=["#2e7d32" if v >= 0 else "#c62828" for v in vals], width=0.55)
        for b, v in zip(bars, fcf_y):
            ax2.annotate("n/a" if v is None else f"{v:.1f}%", (b.get_x() + b.get_width() / 2, b.get_height()),
                         textcoords="offset points", xytext=(0, 3 if (v or 0) >= 0 else -12),
                         ha="center", fontsize=9)
        ax2.axhline(0, color="black", lw=0.8)
        ax2.margins(y=0.3)
        ax2.set_title("FCF yield (FCF / market cap at fiscal year end)", fontsize=11)
        ax2.set_ylabel("%")
        ax2.grid(axis="y", alpha=0.3)
        plt.tight_layout()
        plot_path = f"{save_path}/valuation.png" if save_path and os.path.isdir(save_path) else save_path
        plt.savefig(plot_path, dpi=150)
        plt.close()
        return f"valuation chart ({label}, FCF yield) saved to <img {plot_path}>"

    def _get_pe_eps_performance_original(
        ticker_symbol: Annotated[
            str, "Ticker symbol of the stock (e.g., 'AAPL' for Apple)"
        ],
        filing_date: Annotated[str | datetime, "filing date in 'YYYY-MM-DD' format"],
        years: Annotated[int, "number of years to search from, default to 4"] = 4,
        save_path: Annotated[str, "File path where the plot should be saved"] = None,
    ) -> str:
        """Plot the PE ratio and EPS performance of a company over the past n years."""
        if isinstance(filing_date, str):
            filing_date = datetime.strptime(filing_date, "%Y-%m-%d")

        ss = YFinanceUtils.get_income_stmt(ticker_symbol)
        eps = ss.loc["Diluted EPS", :]

        # 获取过去5年的历史数据
        # historical_data = self.stock.history(period="5y")
        days = round((years + 1) * 365.25)
        start = (filing_date - timedelta(days=days)).strftime("%Y-%m-%d")
        end = filing_date.strftime("%Y-%m-%d")
        historical_data = YFinanceUtils.get_stock_data(ticker_symbol, start, end)

        # 指定的日期，并确保它们都是UTC时区的
        dates = pd.to_datetime(eps.index[::-1], utc=True)

        # 为了确保我们能够找到最接近的股市交易日，我们将转换日期并查找最接近的日期
        results = {}
        for date in dates:
            # 如果指定日期不是交易日，使用bfill和ffill找到最近的交易日股价
            if date not in historical_data.index:
                close_price = historical_data.asof(date)
            else:
                close_price = historical_data.loc[date]

            results[date] = close_price["Close"]

        pe = [p / e for p, e in zip(results.values(), eps.values[::-1])]
        dates = eps.index[::-1]
        eps = eps.values[::-1]

        info = YFinanceUtils.get_stock_info(ticker_symbol)

        # 创建图形和轴对象
        fig, ax1 = plt.subplots(figsize=(14, 7))
        plt.rcParams.update({"font.size": 20})  # 调整为更大的字体大小

        # 绘制市盈率
        color = "tab:blue"
        ax1.set_xlabel("Date")
        ax1.set_ylabel("PE Ratio", color=color)
        ax1.plot(dates, pe, color=color)
        ax1.tick_params(axis="y", labelcolor=color)
        ax1.grid(True)

        # 创建与ax1共享x轴的第二个轴对象
        ax2 = ax1.twinx()
        color = "tab:red"
        ax2.set_ylabel("EPS", color=color)  # 第二个y轴的标签
        ax2.plot(dates, eps, color=color)
        ax2.tick_params(axis="y", labelcolor=color)

        # 设置标题和x轴标签角度
        plt.title(f'{info["shortName"]} PE Ratios and EPS Over the Past {years} Years')
        plt.xticks(rotation=45)

        # 设置x轴刻度标签
        plt.xticks(dates, [d.strftime("%Y-%m") for d in dates])

        plt.tight_layout()
        # plt.show()
        plot_path = (
            f"{save_path}/pe_performance.png" if os.path.isdir(save_path) else save_path
        )
        plt.savefig(plot_path)
        plt.close()
        return f"pe performance chart saved to <img {plot_path}>"


if __name__ == "__main__":
    # Example usage:
    start_date = "2024-03-01"
    end_date = "2024-04-01"
    save_path = "AAPL_candlestick_chart.png"
    MplFinanceUtils.plot_candlestick_chart("AAPL", start_date, end_date, save_path)
