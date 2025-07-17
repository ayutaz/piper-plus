#!/usr/bin/env python3
"""
Unified TTS evaluation script for piper-plus
Runs multiple evaluation metrics and generates a comprehensive report
"""

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TTSEvaluator:
    def __init__(self, scripts_dir: Path):
        self.scripts_dir = scripts_dir
        self.mcd_script = scripts_dir / "evaluate_mcd.py"
        self.pesq_script = scripts_dir / "evaluate_pesq.py"
        self.utmos_script = scripts_dir / "evaluate_utmos.py"

        # Check if scripts exist
        for script in [self.mcd_script, self.pesq_script, self.utmos_script]:
            if not script.exists():
                logger.warning(f"Script not found: {script}")

    def run_mcd_evaluation(
        self, ref_dir: str, synth_dir: str, output_file: str
    ) -> dict:
        """Run MCD evaluation"""
        if not self.mcd_script.exists():
            return {"error": "MCD script not found"}

        cmd = [
            sys.executable,
            str(self.mcd_script),
            "--reference_dir",
            ref_dir,
            "--synthesized_dir",
            synth_dir,
            "--output",
            output_file,
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            with open(output_file) as f:
                return json.load(f)
        except subprocess.CalledProcessError as e:
            logger.error(f"MCD evaluation failed: {e.stderr}")
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"MCD evaluation error: {e}")
            return {"error": str(e)}

    def run_pesq_evaluation(
        self, ref_dir: str, synth_dir: str, output_file: str
    ) -> dict:
        """Run PESQ evaluation"""
        if not self.pesq_script.exists():
            return {"error": "PESQ script not found"}

        cmd = [
            sys.executable,
            str(self.pesq_script),
            "--reference_dir",
            ref_dir,
            "--synthesized_dir",
            synth_dir,
            "--output",
            output_file,
            "--mode",
            "wb",
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            with open(output_file) as f:
                return json.load(f)
        except subprocess.CalledProcessError as e:
            logger.error(f"PESQ evaluation failed: {e.stderr}")
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"PESQ evaluation error: {e}")
            return {"error": str(e)}

    def run_utmos_evaluation(self, audio_dir: str, output_file: str) -> dict:
        """Run UTMOS evaluation"""
        if not self.utmos_script.exists():
            return {"error": "UTMOS script not found"}

        cmd = [
            sys.executable,
            str(self.utmos_script),
            "--audio_dir",
            audio_dir,
            "--output",
            output_file,
        ]

        # Add device selection if CUDA is available
        try:
            import torch

            if torch.cuda.is_available():
                cmd.extend(["--device", "cuda"])
        except ImportError:
            pass

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            with open(output_file) as f:
                return json.load(f)
        except subprocess.CalledProcessError as e:
            logger.error(f"UTMOS evaluation failed: {e.stderr}")
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"UTMOS evaluation error: {e}")
            return {"error": str(e)}

    def generate_report(self, results: dict, output_file: str):
        """Generate HTML report from evaluation results"""
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>TTS Evaluation Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1, h2 {{ color: #333; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        .metric {{ background-color: #e8f4f8; }}
        .error {{ color: red; }}
        .good {{ color: green; }}
        .average {{ color: orange; }}
        .poor {{ color: red; }}
    </style>
</head>
<body>
    <h1>TTS Evaluation Report</h1>
    <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

    <h2>Evaluation Summary</h2>
    <table>
        <tr>
            <th>Metric</th>
            <th>Value</th>
            <th>Rating</th>
            <th>Description</th>
        </tr>
"""

        # MCD Results
        if "mcd" in results and "statistics" in results["mcd"]:
            mcd_stats = results["mcd"]["statistics"]
            if mcd_stats.get("mean_mcd") is not None:
                mcd_value = mcd_stats["mean_mcd"]
                mcd_rating = self._rate_mcd(mcd_value)
                html_content += f"""
        <tr>
            <td class="metric">MCD (Mel-Cepstral Distortion)</td>
            <td>{mcd_value:.2f}</td>
            <td class="{mcd_rating[0]}">{mcd_rating[1]}</td>
            <td>Lower is better (< 5.0 is good)</td>
        </tr>
"""

        # PESQ Results
        if "pesq" in results and "statistics" in results["pesq"]:
            pesq_stats = results["pesq"]["statistics"]
            if pesq_stats.get("mean_pesq") is not None:
                pesq_value = pesq_stats["mean_pesq"]
                pesq_rating = self._rate_pesq(pesq_value)
                html_content += f"""
        <tr>
            <td class="metric">PESQ (Perceptual Evaluation)</td>
            <td>{pesq_value:.3f}</td>
            <td class="{pesq_rating[0]}">{pesq_rating[1]}</td>
            <td>Scale: 1.0-4.5 (higher is better)</td>
        </tr>
"""

        # UTMOS Results
        if "utmos" in results and "statistics" in results["utmos"]:
            utmos_stats = results["utmos"]["statistics"]
            if utmos_stats.get("mean_mos") is not None:
                utmos_value = utmos_stats["mean_mos"]
                utmos_rating = self._rate_utmos(utmos_value)
                html_content += f"""
        <tr>
            <td class="metric">UTMOS (Predicted MOS)</td>
            <td>{utmos_value:.3f}</td>
            <td class="{utmos_rating[0]}">{utmos_rating[1]}</td>
            <td>Scale: 1.0-5.0 (higher is better)</td>
        </tr>
"""

        html_content += """
    </table>

    <h2>Detailed Statistics</h2>
"""

        # Detailed tables for each metric
        for metric_name, metric_data in results.items():
            if isinstance(metric_data, dict) and "statistics" in metric_data:
                stats = metric_data["statistics"]
                if stats.get("num_samples", 0) > 0:
                    html_content += f"""
    <h3>{metric_name.upper()}</h3>
    <table>
        <tr>
            <th>Statistic</th>
            <th>Value</th>
        </tr>
"""
                    for key, value in stats.items():
                        if value is not None and key != "num_samples":
                            html_content += f"""
        <tr>
            <td>{key.replace('_', ' ').title()}</td>
            <td>{value:.3f if isinstance(value, float) else value}</td>
        </tr>
"""
                    html_content += f"""
        <tr>
            <td>Number of Samples</td>
            <td>{stats.get('num_samples', 0)}</td>
        </tr>
    </table>
"""

        html_content += """
</body>
</html>
"""

        with open(output_file, "w") as f:
            f.write(html_content)

    def _rate_mcd(self, value: float) -> tuple:
        """Rate MCD score (lower is better)"""
        if value < 4.0:
            return ("good", "Excellent")
        elif value < 5.0:
            return ("good", "Good")
        elif value < 6.0:
            return ("average", "Average")
        else:
            return ("poor", "Poor")

    def _rate_pesq(self, value: float) -> tuple:
        """Rate PESQ score (1.0-4.5, higher is better)"""
        if value >= 4.0:
            return ("good", "Excellent")
        elif value >= 3.5:
            return ("good", "Good")
        elif value >= 3.0:
            return ("average", "Average")
        else:
            return ("poor", "Poor")

    def _rate_utmos(self, value: float) -> tuple:
        """Rate UTMOS score (1.0-5.0, higher is better)"""
        if value >= 4.5:
            return ("good", "Excellent")
        elif value >= 4.0:
            return ("good", "Good")
        elif value >= 3.5:
            return ("average", "Average")
        else:
            return ("poor", "Poor")


def main():
    parser = argparse.ArgumentParser(description="Run comprehensive TTS evaluation")

    # Directories
    parser.add_argument(
        "--reference_dir",
        type=str,
        required=True,
        help="Directory containing reference audio files",
    )
    parser.add_argument(
        "--synthesized_dir",
        type=str,
        required=True,
        help="Directory containing synthesized audio files",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        required=True,
        help="Directory to save evaluation results",
    )

    # Optional metrics selection
    parser.add_argument(
        "--metrics",
        nargs="+",
        choices=["mcd", "pesq", "utmos", "all"],
        default=["all"],
        help="Metrics to evaluate (default: all)",
    )

    # Report generation
    parser.add_argument(
        "--generate_report", action="store_true", help="Generate HTML report"
    )

    args = parser.parse_args()

    # Create output directory
    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Initialize evaluator
    scripts_dir = Path(__file__).parent
    evaluator = TTSEvaluator(scripts_dir)

    # Determine which metrics to run
    metrics_to_run = []
    if "all" in args.metrics:
        metrics_to_run = ["mcd", "pesq", "utmos"]
    else:
        metrics_to_run = args.metrics

    # Run evaluations
    results = {}

    if "mcd" in metrics_to_run:
        logger.info("Running MCD evaluation...")
        mcd_output = output_path / "mcd_results.json"
        results["mcd"] = evaluator.run_mcd_evaluation(
            args.reference_dir, args.synthesized_dir, str(mcd_output)
        )

    if "pesq" in metrics_to_run:
        logger.info("Running PESQ evaluation...")
        pesq_output = output_path / "pesq_results.json"
        results["pesq"] = evaluator.run_pesq_evaluation(
            args.reference_dir, args.synthesized_dir, str(pesq_output)
        )

    if "utmos" in metrics_to_run:
        logger.info("Running UTMOS evaluation...")
        utmos_output = output_path / "utmos_results.json"
        results["utmos"] = evaluator.run_utmos_evaluation(
            args.synthesized_dir, str(utmos_output)
        )

    # Save combined results
    combined_output = output_path / "evaluation_results.json"
    with open(combined_output, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Combined results saved to {combined_output}")

    # Generate report
    if args.generate_report:
        report_output = output_path / "evaluation_report.html"
        evaluator.generate_report(results, str(report_output))
        logger.info(f"HTML report saved to {report_output}")

        # Print summary
        print("\n=== Evaluation Summary ===")
        for metric, data in results.items():
            if isinstance(data, dict) and "statistics" in data:
                stats = data["statistics"]
                if metric == "mcd" and stats.get("mean_mcd") is not None:
                    print(f"MCD: {stats['mean_mcd']:.2f} (lower is better)")
                elif metric == "pesq" and stats.get("mean_pesq") is not None:
                    print(f"PESQ: {stats['mean_pesq']:.3f} (scale: 1.0-4.5)")
                elif metric == "utmos" and stats.get("mean_mos") is not None:
                    print(f"UTMOS: {stats['mean_mos']:.3f} (scale: 1.0-5.0)")


if __name__ == "__main__":
    main()
