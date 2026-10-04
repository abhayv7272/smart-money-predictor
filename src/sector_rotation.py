class SectorRotationAnalyzer:
    def __init__(self):
        pass

    def analyze_sectors(self, sector_list):
        if not sector_list:
            return {
                "top_leaders": [],
                "improving": [],
                "laggards": [],
                "rotation_summary": "Sector data currently unavailable."
            }
            
        top_leaders = [s for s in sector_list if s["status_code"] == "LEADER"]
        improving = [s for s in sector_list if s["status_code"] == "IMPROVING"]
        neutral = [s for s in sector_list if s["status_code"] == "NEUTRAL"]
        laggards = [s for s in sector_list if s["status_code"] == "LAGGARD"]
        
        # Build institutional sector rotation summary
        leader_names = ", ".join([s["name"] for s in top_leaders[:2]]) if top_leaders else "Broad Index"
        laggard_names = ", ".join([s["name"] for s in laggards[:2]]) if laggards else "None"
        
        if top_leaders:
            summary = f"Institutional accumulation is heavily concentrated in {leader_names}. Focus 10-40 day swing positions in stocks belonging to these leadership sectors. Avoid laggards ({laggard_names})."
        else:
            summary = f"Sector leadership is currently broad-based. Priority to sectors trading above their Daily 20 EMA."
            
        return {
            "all_sectors": sector_list,
            "top_leaders": top_leaders,
            "improving": improving,
            "neutral": neutral,
            "laggards": laggards,
            "rotation_summary": summary
        }
