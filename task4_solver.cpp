// Exact nonnegative scalar shortest paths with directed closures and safe warm starts.
// Reverse Dijkstra on the original graph supplies an admissible, consistent
// heuristic after edge deletion. Disrupted A* searches the WHOLE remaining graph.
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <optional>
#include <queue>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#ifdef _WIN32
#include <windows.h>
#include <psapi.h>
#include <shellapi.h>
#else
#include <sys/resource.h>
#endif
using U=uint64_t;using N=uint32_t;using S=unsigned __int128;
using Cost=std::array<U,5>;using Coeff=std::array<S,5>;
constexpr S INF=S(1)<<126;constexpr N NONE=UINT32_MAX;
namespace fs=std::filesystem;using Clock=std::chrono::steady_clock;
double seconds(Clock::time_point t){return std::chrono::duration<double>(Clock::now()-t).count();}
std::string decimal(S x){if(!x)return "0";std::string s;while(x){s+=char('0'+x%10);x/=10;}std::reverse(s.begin(),s.end());return s;}
S number(const std::string& s){if(s.empty())throw std::runtime_error("empty integer");S x=0;for(char c:s){if(c<'0'||c>'9'||x>(INF-1-(c-'0'))/10)throw std::runtime_error("invalid/overflow integer");x=x*10+(c-'0');}return x;}
N node(const std::string& s){S x=number(s);if(x>=NONE-1)throw std::runtime_error("node out of range");return N(x);}
U peak_mb(){
#ifdef _WIN32
    PROCESS_MEMORY_COUNTERS p{};if(GetProcessMemoryInfo(GetCurrentProcess(),&p,sizeof(p)))return p.PeakWorkingSetSize/(1024*1024);
#else
    rusage p{};if(getrusage(RUSAGE_SELF,&p)==0)return U(p.ru_maxrss)/1024;
#endif
    return 0;
}
struct Raw{N u,v;std::array<N,5> c;};
struct Edge{N to;std::array<N,5> c;};
struct Back{N from,k;};
struct Graph{
    N n=0;std::vector<N> off,roff;std::vector<Edge> edges;std::vector<Back> reverse;std::vector<bool> blocked;
    size_t closed_count=0,removed=0;
    Graph(const fs::path& file,const fs::path& closures){
        std::ifstream in(file);if(!in)throw std::runtime_error("cannot open graph");
        std::vector<Raw> raw;std::string line;
        while(std::getline(in,line)){
            auto first=line.find_first_not_of(" \t\r");if(first==std::string::npos||line[first]=='#')continue;
            std::istringstream row(line);std::array<std::string,7> x;std::string extra;
            for(auto& s:x)if(!(row>>s))throw std::runtime_error("truncated edge");
            if(row>>extra)throw std::runtime_error("extra edge column");
            Raw e{node(x[0]),node(x[1]),{}};
            for(int j=0;j<5;++j){S v=number(x[j+2]);if(v>UINT32_MAX)throw std::runtime_error("edge cost too large");e.c[j]=N(v);}
            raw.push_back(e);n=std::max(n,std::max(e.u,e.v)+1);
        }
        if(!in.eof()||!n||raw.size()>=NONE)throw std::runtime_error("invalid graph");
        off.resize(n+1);roff.resize(n+1);
        for(auto& e:raw){++off[e.u+1];++roff[e.v+1];}
        for(N v=1;v<=n;++v){off[v]+=off[v-1];roff[v]+=roff[v-1];}
        edges.resize(raw.size());reverse.resize(raw.size());blocked.resize(raw.size());auto a=off,b=roff;
        for(auto& e:raw){N k=a[e.u]++;edges[k]={e.v,e.c};reverse[b[e.v]++]={e.u,k};}
        std::ifstream cf(closures);if(!cf||!std::getline(cf,line))throw std::runtime_error("cannot read closures");
        if(!line.empty()&&line.back()=='\r')line.pop_back();
        if(line!="closed_from,closed_to")throw std::runtime_error("invalid closure header");
        std::set<std::pair<N,N>> pairs;
        while(std::getline(cf,line)){
            if(!line.empty()&&line.back()=='\r')line.pop_back();
            if(line.empty())continue;
            auto p=line.find(',');if(p==std::string::npos)throw std::runtime_error("bad closure row");
            auto pair=std::make_pair(node(line.substr(0,p)),node(line.substr(p+1)));
            if(!pairs.insert(pair).second)throw std::runtime_error("duplicate closure");
        }
        if(!cf.eof())throw std::runtime_error("closure read failed");
        closed_count=pairs.size();
        auto missing=pairs;
        for(N u=0;u<n;++u)for(N k=off[u];k<off[u+1];++k)if(pairs.count({u,edges[k].to})){
            blocked[k]=true;++removed;missing.erase({u,edges[k].to});
        }
        if(!missing.empty())throw std::runtime_error("closed pair not present in graph");
    }
};
S dot(const Cost& c,const Coeff& a){S x=0;for(int j=0;j<5;++j){if(c[j]&&a[j]>(INF-1-x)/c[j])throw std::runtime_error("scalar overflow");x+=a[j]*c[j];}return x;}
struct Path{Cost c{};std::vector<N> vertices,edges;S value=0;};
Path recover(const Graph& g,N s,N t,const std::vector<N>& ids,const Coeff& a,bool disrupted){
    Path p;p.vertices.push_back(s);N v=s;std::vector<bool> seen(g.n);seen[v]=true;
    for(N k:ids){
        if(k<g.off[v]||k>=g.off[v+1]||(disrupted&&g.blocked[k]))throw std::runtime_error("invalid/closed path edge");
        v=g.edges[k].to;if(seen[v])throw std::runtime_error("repeated vertex");seen[v]=true;p.vertices.push_back(v);p.edges.push_back(k);
        for(int j=0;j<5;++j){if(p.c[j]>UINT64_MAX-g.edges[k].c[j])throw std::runtime_error("cost overflow");p.c[j]+=g.edges[k].c[j];}
    }
    if(v!=t)throw std::runtime_error("wrong path endpoint");
    p.value=dot(p.c,a);return p;
}
std::optional<Path> input_path(std::istream& in,const Graph& g,N s,N t,const Coeff& a,bool disrupted){
    std::string count;if(!(in>>count))throw std::runtime_error("missing path");if(count=="-1")return std::nullopt;
    S nn=number(count);if(nn>=g.n)throw std::runtime_error("path too long");std::vector<N> ids;
    for(size_t i=0;i<size_t(nn);++i){std::string x;if(!(in>>x))throw std::runtime_error("truncated path");S k=number(x);if(k>=g.edges.size())throw std::runtime_error("bad edge index");ids.push_back(N(k));}
    return recover(g,s,t,ids,a,disrupted);
}
using Item=std::pair<S,N>;
struct Heuristic{std::vector<S> d;std::vector<N> next;};
Heuristic reverse_dijkstra(const Graph& g,N t,const std::vector<S>& cost){
    Heuristic h{std::vector<S>(g.n,INF),std::vector<N>(g.n,NONE)};
    std::priority_queue<Item,std::vector<Item>,std::greater<Item>> q;h.d[t]=0;q.push({0,t});
    while(!q.empty()){
        auto [dv,v]=q.top();q.pop();if(dv!=h.d[v])continue;
        for(N k=g.roff[v];k<g.roff[v+1];++k){auto e=g.reverse[k];S nd=dv+cost[e.k];
            if(nd<h.d[e.from]){h.d[e.from]=nd;h.next[e.from]=e.k;q.push({nd,e.from});}
        }
    }
    return h;
}
std::optional<Path> reference_path(const Graph& g,N s,N t,const Heuristic& h,const Coeff& a){
    if(h.d[s]==INF)return std::nullopt;
    std::vector<N> ids;N v=s;
    while(v!=t){N k=h.next[v];if(k==NONE||ids.size()>=g.n)throw std::runtime_error("bad original shortest-path tree");ids.push_back(k);v=g.edges[k].to;}
    auto p=recover(g,s,t,ids,a,false);if(p.value!=h.d[s])throw std::runtime_error("reference distance mismatch");return p;
}
struct Replan{std::optional<Path> path;U expanded=0;};
Replan astar(const Graph& g,N s,N t,const Coeff& a,const std::vector<S>& cost,const Heuristic& h,std::optional<Path> incumbent){
    Replan r{std::move(incumbent),0};if(h.d[s]==INF)return r;
    S upper=r.path?r.path->value:INF;
    std::vector<S> d(g.n,INF);std::vector<N> prev(g.n,NONE),from(g.n,NONE);std::vector<bool> closed(g.n);
    std::priority_queue<Item,std::vector<Item>,std::greater<Item>> q;d[s]=0;q.push({h.d[s],s});
    while(!q.empty()){
        auto [fv,v]=q.top();q.pop();if(fv>=upper)break;
        if(closed[v]||d[v]+h.d[v]!=fv)continue;
        closed[v]=true;++r.expanded;
        if(v==t){std::vector<N> ids;for(N u=t;u!=s;u=from[u]){if(prev[u]==NONE||ids.size()>=g.n)throw std::runtime_error("bad A* parent chain");ids.push_back(prev[u]);}
            std::reverse(ids.begin(),ids.end());r.path=recover(g,s,t,ids,a,true);if(r.path->value!=d[t])throw std::runtime_error("A* value mismatch");return r;}
        for(N k=g.off[v];k<g.off[v+1];++k){N w=g.edges[k].to;if(g.blocked[k]||closed[w]||h.d[w]==INF)continue;S nd=d[v]+cost[k];
            if(nd<d[w]&&nd+h.d[w]<upper){d[w]=nd;prev[w]=k;from[w]=v;q.push({nd+h.d[w],w});}}
    }
    return r;
}
void path_json(std::ostream& out,const std::optional<Path>& p){
    if(!p){out<<"null";return;}out<<"{\"cost\":[";
    for(int j=0;j<5;++j){if(j)out<<',';out<<p->c[j];}out<<"],\"vertices\":[";
    for(size_t j=0;j<p->vertices.size();++j){if(j)out<<',';out<<p->vertices[j];}out<<"],\"edge_indices\":[";
    for(size_t j=0;j<p->edges.size();++j){if(j)out<<',';out<<p->edges[j];}out<<"],\"scalar\":\""<<decimal(p->value)<<"\"}";
}
int main(int argc,char** argv){
    try{
        std::vector<std::string> args;
#ifdef _WIN32
        int n=0;auto wide=CommandLineToArgvW(GetCommandLineW(),&n);if(!wide)throw std::runtime_error("command line decode failed");
        for(int i=1;i<n;++i){int len=WideCharToMultiByte(CP_UTF8,0,wide[i],-1,nullptr,0,nullptr,nullptr);std::string x(len,'\0');WideCharToMultiByte(CP_UTF8,0,wide[i],-1,x.data(),len,nullptr,nullptr);x.pop_back();args.push_back(x);}LocalFree(wide);(void)argc;(void)argv;
#else
        for(int i=1;i<argc;++i)args.push_back(argv[i]);
#endif
        fs::path edgefile,closures,job,output;
        for(size_t i=0;i<args.size();++i){auto key=args[i];if(i+1==args.size())throw std::runtime_error("missing value");auto v=fs::u8path(args[++i]);
            if(key=="--edges")edgefile=v;else if(key=="--closed")closures=v;else if(key=="--job")job=v;else if(key=="--output")output=v;else throw std::runtime_error("unknown option");}
        if(edgefile.empty()||closures.empty()||job.empty()||output.empty()||fs::exists(output))throw std::runtime_error("missing input or existing output");
        auto start=Clock::now();Graph g(edgefile,closures);double load_time=seconds(start);
        std::ifstream in(job);std::string version,x,y,count;if(!(in>>version>>x>>y>>count)||version!="TASK4_JOB_V1")throw std::runtime_error("bad job header");
        N s=node(x),t=node(y);S ns=number(count);if(s>=g.n||t>=g.n||ns<1||ns>100)throw std::runtime_error("invalid job dimensions");
        std::ostringstream out;out<<std::setprecision(10)<<"{\"schema\":\"TASK4_V1\",\"source\":"<<s<<",\"target\":"<<t<<",\"closed_pairs\":"<<g.closed_count<<",\"removed_edges\":"<<g.removed<<",\"load_seconds\":"<<load_time<<",\"schemes\":[";
        for(size_t z=0;z<size_t(ns);++z){
            std::string name;if(!(in>>name)||name.find_first_not_of("abcdefghijklmnopqrstuvwxyz_0123456789")!=std::string::npos)throw std::runtime_error("invalid scheme");
            Coeff a{};for(auto& v:a){std::string w;if(!(in>>w))throw std::runtime_error("missing coefficient");v=number(w);}if(std::all_of(a.begin(),a.end(),[](S v){return v==0;}))throw std::runtime_error("zero objective");
            auto original=input_path(in,g,s,t,a,false),warm=input_path(in,g,s,t,a,true);
            auto tick=Clock::now();std::vector<S> cost(g.edges.size());S mx=0;
            for(N k=0;k<g.edges.size();++k){Cost c{};for(int j=0;j<5;++j)c[j]=g.edges[k].c[j];cost[k]=dot(c,a);mx=std::max(mx,cost[k]);}
            if(mx>=(INF-1)/(2ULL*g.n+1))throw std::runtime_error("scalar costs exceed search capacity");
            double scalar_time=seconds(tick);
            tick=Clock::now();auto h=reverse_dijkstra(g,t,cost);auto reference=reference_path(g,s,t,h,a);double reference_time=seconds(tick);
            if(bool(original)!=bool(reference))throw std::runtime_error("candidate set reachability mismatch");
            tick=Clock::now();auto result=astar(g,s,t,a,cost,h,warm);double replan_time=seconds(tick);
            if(result.path&&reference&&result.path->value<reference->value)throw std::runtime_error("closure improved exact optimum");
            if(z)out<<',';
            out<<"{\"name\":\""<<name<<"\",\"coefficients\":[";
            for(int j=0;j<5;++j){if(j)out<<',';out<<'"'<<decimal(a[j])<<'"';}out<<"],\"original\":";path_json(out,original);
            out<<",\"original_optimal\":";path_json(out,reference);out<<",\"warm_start\":";path_json(out,warm);out<<",\"disrupted\":";path_json(out,result.path);
            out<<",\"scalar_seconds\":"<<scalar_time<<",\"reference_seconds\":"<<reference_time<<",\"replan_seconds\":"<<replan_time<<",\"expanded\":"<<result.expanded<<'}';
        }
        std::string extra;if(in>>extra)throw std::runtime_error("extra job token");
        out<<"],\"total_seconds\":"<<seconds(start)<<",\"peak_rss_mb\":"<<peak_mb()<<"}\n";
        if(!output.parent_path().empty())fs::create_directories(output.parent_path());
        std::ofstream file(output);file<<out.str();file.close();if(!file)throw std::runtime_error("write failed");
        std::cout<<"complete schemes="<<size_t(ns)<<" total_s="<<seconds(start)<<" peak_mb="<<peak_mb()<<'\n';return 0;
    }catch(const std::exception& e){std::cerr<<"ERROR: "<<e.what()<<'\n';return 1;}
}
